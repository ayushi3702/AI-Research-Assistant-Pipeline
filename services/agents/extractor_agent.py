"""
Extractor Agent — second stage of the research pipeline.

Fetches the full content of each discovered source (HTML via Playwright/
BeautifulSoup, PDFs via PyMuPDF), splits it into passages, and scores each
passage's relevance to the query with GPT, producing ranked ExtractedChunks.
"""
from __future__ import annotations
import asyncio
import json
import os
import datetime
import logging
import io

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from playwright.async_api import async_playwright

from shared.state import ResearchState, ExtractedChunk
from shared.database import SessionLocal, AgentTask, Source

logger = logging.getLogger(__name__)
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    max_tokens=5,
)

MAX_CHUNK_CHARS = 1500
MAX_URLS = 8  # cap to avoid long runtimes


# ── Fetch helpers ─────────────────────────────────────────────────────────────

async def _fetch_html(url: str) -> str:
    """Use Playwright to fetch JS-rendered pages."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            html = await page.content()
            await browser.close()
        soup = BeautifulSoup(html, "html.parser")
        # Strip nav/footer/scripts for cleaner text
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except Exception as e:
        logger.warning(f"[extractor] HTML fetch failed for {url}: {e}")
        return ""


async def _fetch_pdf(url: str) -> str:
    """Download and extract text from a PDF URL."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.get(url)
        doc = fitz.open(stream=io.BytesIO(resp.content), filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        logger.warning(f"[extractor] PDF fetch failed for {url}: {e}")
        return ""


async def _fetch_content(url: str) -> str:
    """Dispatch to the PDF or HTML fetcher based on the URL shape."""
    if url.endswith(".pdf") or "arxiv.org/pdf" in url:
        return await _fetch_pdf(url)
    return await _fetch_html(url)


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks, current = [], []
    length = 0
    for word in words:
        current.append(word)
        length += len(word) + 1
        if length >= chunk_size:
            chunks.append(" ".join(current))
            current = current[-50:]  # 50-word overlap
            length = sum(len(w) + 1 for w in current)
    if current:
        chunks.append(" ".join(current))
    return chunks


# ── Relevance scoring via GPT ─────────────────────────────────────────────────

async def _score_chunk(query: str, chunk: str) -> float:
    """Ask GPT to score chunk relevance 0.0–1.0."""
    try:
        response = await llm.ainvoke([
            SystemMessage(content=(
                "Score how relevant this text chunk is to the research query. "
                "Respond with ONLY a number between 0.0 and 1.0."
            )),
            HumanMessage(content=f"Query: {query}\n\nChunk: {chunk[:600]}"),
        ])
        return float(response.content.strip())
    except Exception:
        logger.warning(
            "Failed to score chunk relevance; defaulting to 0.5", exc_info=True
        )
        return 0.5


# ── Agent entry point ─────────────────────────────────────────────────────────

async def extractor_agent(state: ResearchState) -> dict:
    """
    For each search result URL, fetch content, chunk it,
    score relevance, and keep the top chunks.
    """
    started = datetime.datetime.utcnow()
    db = SessionLocal()
    task = AgentTask(
        job_id=state.job_id,
        agent_name="extractor",
        status="running",
        input_data=json.dumps({"url_count": len(state.search_results)}),
        started_at=started,
    )
    db.add(task)
    db.commit()

    all_chunks: list[ExtractedChunk] = []
    urls = [r.url for r in state.search_results[:MAX_URLS]]

    try:
        # Fetch all URLs concurrently
        contents = await asyncio.gather(*[_fetch_content(url) for url in urls])

        # Chunk + score concurrently
        score_tasks = []
        chunk_meta = []
        for url, content, result in zip(urls, contents, state.search_results[:MAX_URLS]):
            if not content.strip():
                continue
            for chunk in _chunk_text(content)[:5]:  # max 5 chunks per URL
                score_tasks.append(_score_chunk(state.query, chunk))
                chunk_meta.append((url, chunk, result.source_type))

        scores = await asyncio.gather(*score_tasks)

        for (url, chunk, source_type), score in zip(chunk_meta, scores):
            if score >= 0.4:  # relevance threshold
                ec = ExtractedChunk(
                    url=url,
                    content=chunk,
                    relevance_score=round(score, 3),
                    source_type=source_type,
                )
                all_chunks.append(ec)

                # Persist to DB
                db.add(Source(
                    job_id=state.job_id,
                    url=url,
                    relevance_score=score,
                    content_chunk=chunk,
                    source_type=source_type,
                ))

        db.commit()

        # Sort by relevance, keep top 20
        all_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        top_chunks = all_chunks[:20]

        finished = datetime.datetime.utcnow()
        task.status = "done"
        task.output_data = json.dumps({"chunk_count": len(top_chunks)})
        task.finished_at = finished
        task.duration_ms = (finished - started).total_seconds() * 1000
        db.commit()

        logger.info(f"[extractor_agent] Extracted {len(top_chunks)} relevant chunks")
        return {
            "chunks": top_chunks,
            "completed_agents": ["extractor"],
        }

    except Exception as e:
        task.status = "failed"
        db.commit()
        logger.error(f"[extractor_agent] Error: {e}")
        return {"errors": [f"extractor_agent: {str(e)}"]}

    finally:
        db.close()
