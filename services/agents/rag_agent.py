"""
RAG Agent — Retrieval-Augmented Generation step in the research pipeline.

This agent:
1. Stores the current job's extracted chunks in the vector store.
2. Retrieves relevant context from past research jobs to augment the writer.
"""
from __future__ import annotations
import json
import datetime
import logging

from shared.state import ResearchState
from shared.database import SessionLocal, AgentTask
from shared.vector_store import store_chunks, retrieve_relevant_chunks

logger = logging.getLogger(__name__)


async def rag_agent(state: ResearchState) -> dict:
    """
    RAG agent entry point:
    - Indexes current chunks into the vector store for future retrieval.
    - Queries the vector store for relevant past research context.
    """
    started = datetime.datetime.utcnow()
    db = SessionLocal()
    task = AgentTask(
        job_id=state.job_id,
        agent_name="rag",
        status="running",
        input_data=json.dumps({
            "query": state.query,
            "chunks_count": len(state.chunks),
        }),
        started_at=started,
    )
    db.add(task)
    db.commit()

    try:
        # Step 1: Store current job's chunks in the vector store
        chunks_to_store = [
            {
                "content": chunk.content,
                "url": chunk.url,
                "source_type": chunk.source_type,
                "relevance_score": chunk.relevance_score,
            }
            for chunk in state.chunks
        ]
        stored_count = store_chunks(chunks_to_store, state.job_id)
        logger.info(f"[rag_agent] Indexed {stored_count} chunks for job {state.job_id}")

        # Step 2: Retrieve relevant chunks from past jobs
        retrieved = retrieve_relevant_chunks(
            query=state.query,
            n_results=8,
            exclude_job_id=state.job_id,
        )

        # Filter to only reasonably relevant results (cosine distance < 0.7)
        rag_context = [
            {
                "content": r["content"],
                "url": r["url"],
                "source_type": r["source_type"],
                "distance": r["distance"],
                "from_job": r["job_id"],
            }
            for r in retrieved
            if r["distance"] < 0.7
        ]

        logger.info(
            f"[rag_agent] Retrieved {len(rag_context)} relevant past chunks "
            f"(from {len(retrieved)} candidates)"
        )

        finished = datetime.datetime.utcnow()
        task.status = "done"
        task.output_data = json.dumps({
            "stored_chunks": stored_count,
            "retrieved_chunks": len(rag_context),
        })
        task.finished_at = finished
        task.duration_ms = (finished - started).total_seconds() * 1000
        db.commit()

        return {
            "rag_context": rag_context,
            "completed_agents": ["rag"],
        }

    except Exception as e:
        task.status = "failed"
        task.finished_at = datetime.datetime.utcnow()
        db.commit()
        logger.error(f"[rag_agent] Error: {e}")
        return {"errors": [f"rag_agent: {str(e)}"]}
    finally:
        db.close()
