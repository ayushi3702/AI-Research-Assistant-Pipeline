from __future__ import annotations
import asyncio
import json
import os
import datetime
import logging

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from tavily import TavilyClient
import arxiv

from shared.state import ResearchState, SearchResult
from shared.database import SessionLocal, AgentTask

logger = logging.getLogger(__name__)

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


# ── LangChain tool definitions ────────────────────────────────────────────────

@tool
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web for recent information on a topic using Tavily."""
    response = tavily.search(query=query, max_results=max_results)
    return [
        {"url": r["url"], "title": r.get("title", ""), "snippet": r.get("content", ""), "source_type": "web"}
        for r in response.get("results", [])
    ]


@tool
def arxiv_search(query: str, max_results: int = 3) -> list[dict]:
    """Search Arxiv for academic papers related to a topic."""
    search = arxiv.Search(query=query, max_results=max_results)
    client = arxiv.Client()
    results = []
    for paper in client.results(search):
        results.append({
            "url": paper.entry_id,
            "title": paper.title,
            "snippet": paper.summary[:400],
            "source_type": "arxiv",
        })
    return results


TOOLS = [web_search, arxiv_search]
llm_with_tools = llm.bind_tools(TOOLS)


# ── Agent entry point ─────────────────────────────────────────────────────────

async def search_agent(state: ResearchState) -> dict:
    """
    Calls GPT-5.2 with web_search and arxiv_search tools.
    The model decides how many searches to run and what queries to use.
    """
    started = datetime.datetime.utcnow()
    db = SessionLocal()
    task = AgentTask(
        job_id=state.job_id,
        agent_name="search",
        status="running",
        input_data=json.dumps({"query": state.query}),
        started_at=started,
    )
    db.add(task)
    db.commit()

    all_results: list[SearchResult] = []

    try:
        messages = [
            SystemMessage(content=(
                "You are a research search agent. Given a research topic, "
                "run multiple targeted web and arxiv searches to collect diverse, "
                "high-quality sources. Use 3-5 searches with varied query angles."
            )),
            HumanMessage(content=f"Research topic: {state.query}"),
        ]

        tool_map = {"web_search": web_search, "arxiv_search": arxiv_search}

        # Agentic tool-use loop — keep calling until the model stops using tools
        for _ in range(6):  # max 6 tool rounds
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break  # model is done searching

            # Execute all tool calls
            for tc in response.tool_calls:
                tool_fn = tool_map[tc["name"]]
                result = await asyncio.to_thread(tool_fn.invoke, tc["args"])
                for r in result:
                    all_results.append(SearchResult(
                        url=r["url"],
                        title=r["title"],
                        snippet=r["snippet"],
                        source_type=r["source_type"],
                    ))
                messages.append(ToolMessage(
                    content=json.dumps(result),
                    tool_call_id=tc["id"],
                ))

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[SearchResult] = []
        for r in all_results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)

        finished = datetime.datetime.utcnow()
        duration = (finished - started).total_seconds() * 1000

        task.status = "done"
        task.output_data = json.dumps({"result_count": len(unique)})
        task.finished_at = finished
        task.duration_ms = duration
        db.commit()

        logger.info(f"[search_agent] Found {len(unique)} unique sources")
        return {
            "search_results": unique,
            "completed_agents": ["search"],
        }

    except Exception as e:
        task.status = "failed"
        db.commit()
        logger.error(f"[search_agent] Error: {e}")
        return {"errors": [f"search_agent: {str(e)}"]}

    finally:
        db.close()
