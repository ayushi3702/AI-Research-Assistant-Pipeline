from __future__ import annotations
import asyncio
import json
import logging
import os
import traceback
import uuid
import datetime

from langgraph.graph import StateGraph, END

from shared.state import ResearchState
from shared.message_bus import bus
from shared.database import SessionLocal, ResearchJob, ReasoningTrace, init_db
from shared.audit import audit
from agents.search_agent import search_agent
from agents.extractor_agent import extractor_agent
from agents.validator_agent import validator_agent
from agents.rag_agent import rag_agent
from agents.writer_agent import writer_agent

logger = logging.getLogger(__name__)

# ── Routing logic ─────────────────────────────────────────────────────────────

def should_continue_after_search(state: ResearchState) -> str:
    """After search: proceed to extraction, or fail if nothing found."""
    if state.errors and not state.search_results:
        logger.warning("No search results — aborting pipeline")
        return "end"
    if len(state.search_results) == 0:
        return "end"
    return "extractor"


def should_continue_after_extraction(state: ResearchState) -> str:
    """After extraction: skip validation if no chunks, else validate."""
    if not state.chunks:
        logger.warning("No chunks extracted — skipping to writer with raw search results")
        return "writer"
    return "validator"


def should_continue_after_validation(state: ResearchState) -> str:
    """After validation: proceed to RAG retrieval."""
    return "rag"


def should_continue_after_rag(state: ResearchState) -> str:
    """After RAG: always proceed to writer."""
    return "writer"


# ── Status broadcast (for WebSocket streaming) ────────────────────────────────

async def _broadcast_status(job_id: str, agent: str, status: str) -> None:
    payload = {"job_id": job_id, "agent": agent, "status": status}
    await bus.publish(f"status:{job_id}", json.dumps(payload))


async def _broadcast_log(job_id: str, agent: str, message: str) -> None:
    payload = {"job_id": job_id, "type": "log", "agent": agent, "message": message}
    await bus.publish(f"status:{job_id}", json.dumps(payload))


async def _broadcast_reasoning(job_id: str, agent: str, step: str, reasoning: str, decision: str = "", metadata: dict | None = None) -> None:
    """Broadcast a reasoning trace event to the WebSocket channel and persist to DB."""
    payload = {
        "job_id": job_id,
        "type": "reasoning",
        "agent": agent,
        "step": step,
        "reasoning": reasoning,
        "decision": decision,
        "metadata": metadata or {},
        "timestamp": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat(),
    }
    await bus.publish(f"status:{job_id}", json.dumps(payload))

    # Persist to DB (non-blocking)
    try:
        db = SessionLocal()
        trace = ReasoningTrace(
            job_id=job_id,
            agent=agent,
            step=step,
            reasoning=reasoning,
            decision=decision,
            trace_metadata=json.dumps(metadata or {}),
        )
        db.add(trace)
        db.commit()
        db.close()
    except Exception:
        pass  # Don't fail the pipeline for trace persistence issues


def _audit_node_result(state: ResearchState, agent: str, result: dict, status: str) -> None:
    """Record an audit entry whenever an agent reports an error / failed status."""
    if status == "failed":
        errors = result.get("errors") or []
        audit(
            "agent_failed",
            level="error",
            job_id=state.job_id,
            agent=agent,
            message=f"Agent '{agent}' reported a failure",
            detail={"errors": errors},
        )


# ── Node wrappers (inject status broadcasts) ──────────────────────────────────

async def search_node(state: ResearchState) -> dict:
    await _broadcast_status(state.job_id, "search", "running")
    await _broadcast_reasoning(state.job_id, "search", "strategy",
        f"Analyzing query to determine optimal search strategy",
        f"Will use multi-angle searches with web + academic sources for: '{state.query}'",
        {"query": state.query})
    await _broadcast_log(state.job_id, "search", f"Searching for: {state.query}")
    result = await search_agent(state)
    n_results = len(result.get("search_results", []))
    # Analyze source diversity
    sources = result.get("search_results", [])
    web_count = sum(1 for s in sources if getattr(s, 'source_type', 'web') == 'web')
    arxiv_count = sum(1 for s in sources if getattr(s, 'source_type', '') == 'arxiv')
    await _broadcast_reasoning(state.job_id, "search", "results_analysis",
        f"Collected {n_results} sources: {web_count} web pages, {arxiv_count} academic papers",
        f"Sufficient diversity achieved — proceeding to extraction",
        {"total": n_results, "web": web_count, "arxiv": arxiv_count})
    await _broadcast_log(state.job_id, "search", f"Found {n_results} results")
    status = "done" if "errors" not in result or not result["errors"] else "failed"
    _audit_node_result(state, "search", result, status)
    if status != "failed" and n_results == 0:
        audit("no_search_results", level="warning", job_id=state.job_id, agent="search",
              message=f"Search returned no results for query: {state.query!r}")
    await _broadcast_status(state.job_id, "search", status)
    return result


async def extractor_node(state: ResearchState) -> dict:
    await _broadcast_status(state.job_id, "extractor", "running")
    n_urls = len(state.search_results)
    await _broadcast_reasoning(state.job_id, "extractor", "planning",
        f"Need to extract content from {n_urls} sources",
        f"Will fetch and chunk up to {min(n_urls, 8)} pages, prioritizing diverse source types",
        {"url_count": n_urls})
    await _broadcast_log(state.job_id, "extractor", f"Extracting content from {n_urls} sources")
    result = await extractor_agent(state)
    n_chunks = len(result.get("chunks", []))
    await _broadcast_reasoning(state.job_id, "extractor", "extraction_complete",
        f"Extracted {n_chunks} relevant text chunks from sources",
        "Chunks scored by relevance — top chunks will be used for validation and writing" if n_chunks > 0 else "No usable content found — will skip validation",
        {"chunk_count": n_chunks})
    await _broadcast_log(state.job_id, "extractor", f"Extracted {n_chunks} text chunks")
    status = "done" if "errors" not in result or not result["errors"] else "failed"
    _audit_node_result(state, "extractor", result, status)
    await _broadcast_status(state.job_id, "extractor", status)
    # If no chunks extracted, validator and rag will be skipped — notify UI
    chunks = result.get("chunks", state.chunks)
    if not chunks:
        audit("no_chunks_extracted", level="warning", job_id=state.job_id, agent="extractor",
              message="No text chunks extracted — skipping validator & RAG, writer will use raw snippets",
              detail={"source_count": n_urls})
        await _broadcast_reasoning(state.job_id, "extractor", "skip_decision",
            "No text chunks extracted from any source",
            "Skipping validator and RAG agents — writer will use raw search snippets")
        await _broadcast_log(state.job_id, "extractor", "No chunks — skipping validator & RAG")
        await _broadcast_status(state.job_id, "validator", "skipped")
        await _broadcast_status(state.job_id, "rag", "skipped")
    return result


async def validator_node(state: ResearchState) -> dict:
    await _broadcast_status(state.job_id, "validator", "running")
    await _broadcast_reasoning(state.job_id, "validator", "claim_extraction",
        f"Analyzing {len(state.chunks)} chunks to identify key factual claims",
        "Will extract 5-8 verifiable claims and cross-reference against source material",
        {"chunk_count": len(state.chunks)})
    await _broadcast_log(state.job_id, "validator", f"Validating {len(state.chunks)} chunks for accuracy")
    result = await validator_agent(state)
    n_claims = len(result.get("validated_claims", []))
    # Summarize validation results
    claims = result.get("validated_claims", [])
    verified = sum(1 for c in claims if c.supported_by and not c.contradicted_by)
    disputed = sum(1 for c in claims if c.contradicted_by)
    uncertain = n_claims - verified - disputed
    await _broadcast_reasoning(state.job_id, "validator", "validation_results",
        f"Validated {n_claims} claims: {verified} verified, {uncertain} uncertain, {disputed} contradicted",
        "Flagging contradicted claims for the writer to handle carefully" if disputed > 0 else "All claims have reasonable support — proceeding with high confidence",
        {"verified": verified, "uncertain": uncertain, "disputed": disputed})
    await _broadcast_log(state.job_id, "validator", f"Validated {n_claims} claims")
    status = "done" if "errors" not in result or not result["errors"] else "failed"
    _audit_node_result(state, "validator", result, status)
    await _broadcast_status(state.job_id, "validator", status)
    return result


async def rag_node(state: ResearchState) -> dict:
    await _broadcast_status(state.job_id, "rag", "running")
    await _broadcast_reasoning(state.job_id, "rag", "context_retrieval",
        "Searching vector database for related past research and context",
        "Will augment current findings with relevant historical research data",
        {"existing_chunks": len(state.chunks)})
    await _broadcast_log(state.job_id, "rag", "Storing chunks in vector DB for retrieval")
    result = await rag_agent(state)
    rag_items = len(result.get("rag_context", []))
    await _broadcast_reasoning(state.job_id, "rag", "context_ready",
        f"Retrieved {rag_items} relevant context items from past research",
        "Writer will have access to both fresh sources and historical context" if rag_items > 0 else "No relevant past research found — writer will rely on current sources only",
        {"rag_items": rag_items})
    await _broadcast_log(state.job_id, "rag", "RAG context prepared for writer")
    status = "done" if "errors" not in result or not result["errors"] else "failed"
    _audit_node_result(state, "rag", result, status)
    await _broadcast_status(state.job_id, "rag", status)
    return result


async def writer_node(state: ResearchState) -> dict:
    await _broadcast_status(state.job_id, "writer", "running")
    n_sources = len(state.chunks)
    n_claims = len(state.validated_claims)
    n_rag = len(state.rag_context)
    await _broadcast_reasoning(state.job_id, "writer", "synthesis_planning",
        f"Synthesizing report from {n_sources} source chunks, {n_claims} validated claims, and {n_rag} RAG context items",
        f"Will write a structured report in {state.language} with inline citations and fact-check annotations",
        {"sources": n_sources, "claims": n_claims, "rag_context": n_rag, "language": state.language})
    await _broadcast_log(state.job_id, "writer", "Generating research report with GPT")
    result = await writer_agent(state)
    report = result.get("report", "")
    await _broadcast_reasoning(state.job_id, "writer", "report_complete",
        f"Generated {len(report)} character report with structured sections",
        "Report includes Executive Summary, Key Findings, Analysis, and References",
        {"report_length": len(report)})
    await _broadcast_log(state.job_id, "writer", f"Report generated ({len(report)} chars)")
    status = "done" if "errors" not in result or not result["errors"] else "failed"
    _audit_node_result(state, "writer", result, status)
    if status != "failed" and len(report.strip()) < 200:
        audit("empty_report", level="warning", job_id=state.job_id, agent="writer",
              message=f"Writer produced an unusually short report ({len(report)} chars)")
    await _broadcast_status(state.job_id, "writer", status)
    return result


# ── Build the graph ───────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(ResearchState)

    # Register nodes
    graph.add_node("search",    search_node)
    graph.add_node("extractor", extractor_node)
    graph.add_node("validator", validator_node)
    graph.add_node("rag",       rag_node)
    graph.add_node("writer",    writer_node)

    # Entry point
    graph.set_entry_point("search")

    # Conditional edges
    graph.add_conditional_edges(
        "search",
        should_continue_after_search,
        {"extractor": "extractor", "end": END},
    )
    graph.add_conditional_edges(
        "extractor",
        should_continue_after_extraction,
        {"validator": "validator", "writer": "writer"},
    )
    graph.add_conditional_edges(
        "validator",
        should_continue_after_validation,
        {"rag": "rag"},
    )
    graph.add_conditional_edges(
        "rag",
        should_continue_after_rag,
        {"writer": "writer"},
    )
    graph.add_edge("writer", END)

    return graph.compile()


# Compiled graph — import this in the API
pipeline = build_graph()


# ── Public entry point ────────────────────────────────────────────────────────

async def run_research(query: str, job_id: str | None = None, user_id: str | None = None, language: str = "English") -> ResearchState:
    """
    Main entry point. Creates a DB job record, runs the full pipeline,
    and returns the final state (including the report).
    """
    init_db()

    if job_id is None:
        job_id = str(uuid.uuid4())
    db = SessionLocal()
    job = ResearchJob(id=job_id, query=query, status="running", user_id=user_id)
    db.add(job)
    db.commit()
    db.close()

    logger.info(f"[orchestrator] Starting job {job_id} — query: {query!r}")
    audit("job_started", job_id=job_id, user_id=user_id, agent="orchestrator",
          message=f"Research job started — query: {query!r}")
    await _broadcast_status(job_id, "orchestrator", "running")

    initial_state = ResearchState(job_id=job_id, query=query, language=language)

    try:
        final_state = await pipeline.ainvoke(initial_state)
        await _broadcast_status(job_id, "orchestrator", "done")
        logger.info(f"[orchestrator] Job {job_id} complete")
        audit("job_completed", job_id=job_id, user_id=user_id, agent="orchestrator",
              message="Research job completed successfully")
        return final_state

    except Exception as e:
        db = SessionLocal()
        job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
        db.close()
        await _broadcast_status(job_id, "orchestrator", "failed")
        logger.error(f"[orchestrator] Job {job_id} failed: {e}")
        audit("job_failed", level="error", job_id=job_id, user_id=user_id,
              agent="orchestrator",
              message=f"Research job failed: {e}",
              detail=traceback.format_exc())
        raise


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    query = " ".join(sys.argv[1:])
    if not query:
        print("Usage: python orchestrator.py <query>")
        sys.exit(1)

    result = asyncio.run(run_research(query))
    print("\n" + "=" * 60)
    print(result.get("report", "No report generated"))
