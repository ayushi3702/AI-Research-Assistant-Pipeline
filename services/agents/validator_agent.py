from __future__ import annotations
import json
import os
import datetime
import logging

import chromadb
from chromadb.utils import embedding_functions
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from shared.state import ResearchState, ValidatedClaim
from shared.database import SessionLocal, AgentTask, ClaimVerification

logger = logging.getLogger(__name__)
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
)

# ChromaDB in-memory client (persists for the lifetime of the process)
chroma_client = chromadb.Client()
embed_fn = embedding_functions.DefaultEmbeddingFunction()


# ── Build vector store from extracted chunks ──────────────────────────────────

def _build_collection(state: ResearchState) -> chromadb.Collection:
    col_name = f"job_{state.job_id.replace('-', '_')}"
    try:
        chroma_client.delete_collection(col_name)
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=col_name,
        embedding_function=embed_fn,
    )

    if not state.chunks:
        return collection

    collection.add(
        documents=[c.content for c in state.chunks],
        metadatas=[{"url": c.url, "score": c.relevance_score} for c in state.chunks],
        ids=[f"chunk_{i}" for i in range(len(state.chunks))],
    )
    return collection


# ── Validate a single claim ───────────────────────────────────────────────────

async def _validate_claim(
    claim: str, collection: chromadb.Collection
) -> ValidatedClaim:
    """
    Query the vector store for chunks related to this claim,
    then ask GPT whether they support or contradict it.
    """
    results = collection.query(query_texts=[claim], n_results=min(5, collection.count()))
    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []

    if not docs:
        return ValidatedClaim(claim=claim, supported_by=[], confidence=0.3)

    context = "\n\n".join(
        f"[Source: {m['url']}]\n{d}" for d, m in zip(docs, metas)
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=(
                "You are a fact-checking agent. Given a claim and source excerpts, "
                "identify which URLs support the claim and which contradict it. "
                "Respond ONLY with valid JSON in this exact format:\n"
                '{"supported_by": ["url1"], "contradicted_by": ["url2"], "confidence": 0.9}'
            )),
            HumanMessage(content=f"Claim: {claim}\n\nSources:\n{context}"),
        ],
    )

    try:
        data = json.loads(response.content)
        return ValidatedClaim(
            claim=claim,
            supported_by=data.get("supported_by", []),
            contradicted_by=data.get("contradicted_by", []),
            confidence=float(data.get("confidence", 0.7)),
        )
    except Exception:
        urls = [m["url"] for m in metas]
        return ValidatedClaim(claim=claim, supported_by=urls, confidence=0.5)


# ── Agent entry point ─────────────────────────────────────────────────────────

async def validator_agent(state: ResearchState) -> dict:
    """
    1. Load all chunks into ChromaDB.
    2. Ask GPT to extract key claims from the query + top chunks.
    3. Validate each claim against the vector store.
    """
    started = datetime.datetime.utcnow()
    db = SessionLocal()
    task = AgentTask(
        job_id=state.job_id,
        agent_name="validator",
        status="running",
        input_data=json.dumps({"chunk_count": len(state.chunks)}),
        started_at=started,
    )
    db.add(task)
    db.commit()

    try:
        collection = _build_collection(state)

        # Ask GPT to generate the key claims we should validate
        top_context = "\n\n".join(
            c.content for c in sorted(state.chunks, key=lambda x: x.relevance_score, reverse=True)[:8]
        )
        claims_response = await llm.ainvoke(
            [
                SystemMessage(content=(
                    "Extract 5-8 specific, verifiable factual claims from the provided "
                    "research context that are central to answering the query. "
                    "Return ONLY a JSON array of claim strings."
                )),
                HumanMessage(content=f"Query: {state.query}\n\nContext:\n{top_context}"),
            ],
        )

        raw = json.loads(claims_response.content)
        claims: list[str] = raw.get("claims", raw) if isinstance(raw, dict) else raw
        if not isinstance(claims, list):
            claims = list(raw.values())[0] if isinstance(raw, dict) else []

        # Validate each claim concurrently
        import asyncio
        validated = await asyncio.gather(
            *[_validate_claim(c, collection) for c in claims[:8]]
        )

        finished = datetime.datetime.utcnow()
        task.status = "done"
        task.output_data = json.dumps({"claims_validated": len(validated)})
        task.finished_at = finished
        task.duration_ms = (finished - started).total_seconds() * 1000

        # Persist claim verifications to DB
        for vc in validated:
            status = "verified" if vc.supported_by and not vc.contradicted_by else \
                     "disputed" if vc.contradicted_by else "unverified"
            cv = ClaimVerification(
                job_id=state.job_id,
                claim=vc.claim,
                status=status,
                confidence=vc.confidence,
                supported_by=json.dumps(vc.supported_by),
                contradicted_by=json.dumps(vc.contradicted_by),
            )
            db.add(cv)

        db.commit()

        logger.info(f"[validator_agent] Validated {len(validated)} claims")
        return {
            "validated_claims": list(validated),
            "completed_agents": ["validator"],
        }

    except Exception as e:
        task.status = "failed"
        db.commit()
        logger.error(f"[validator_agent] Error: {e}")
        return {"errors": [f"validator_agent: {str(e)}"]}

    finally:
        db.close()
