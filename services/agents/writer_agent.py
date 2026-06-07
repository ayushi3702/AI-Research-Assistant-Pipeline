from __future__ import annotations
import json
import os
import datetime
import logging

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from shared.state import ResearchState
from shared.database import SessionLocal, AgentTask, ResearchJob, User

logger = logging.getLogger(__name__)
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    max_tokens=2000,
)


def _build_writer_prompt(state: ResearchState) -> str:
    # Top chunks as context
    top_chunks = sorted(state.chunks, key=lambda c: c.relevance_score, reverse=True)[:12]
    context_blocks = "\n\n".join(
        f"[{i+1}] {c.url}\n{c.content}"
        for i, c in enumerate(top_chunks)
    )

    # Validated claims summary
    claims_text = ""
    if state.validated_claims:
        lines = []
        for vc in state.validated_claims:
            status = "✓ Supported" if vc.supported_by and not vc.contradicted_by else \
                     "⚠ Disputed" if vc.contradicted_by else "? Unverified"
            lines.append(f"- {status} (conf={vc.confidence:.1f}): {vc.claim}")
        claims_text = "Validated claims:\n" + "\n".join(lines)

    # RAG context from past research
    rag_text = ""
    if state.rag_context:
        rag_blocks = "\n\n".join(
            f"[Past-{i+1}] {r.get('url', 'unknown')}\n{r['content']}"
            for i, r in enumerate(state.rag_context[:6])
        )
        rag_text = f"Relevant context from past research:\n{rag_blocks}"

    return f"""Research query: {state.query}

{claims_text}

{rag_text}

Source excerpts (numbered for citation):
{context_blocks}"""


async def writer_agent(state: ResearchState) -> dict:
    """
    Synthesizes all gathered information into a structured markdown report
    with inline citations [1], [2], etc.
    """
    started = datetime.datetime.utcnow()
    db = SessionLocal()
    task = AgentTask(
        job_id=state.job_id,
        agent_name="writer",
        status="running",
        input_data=json.dumps({
            "chunks": len(state.chunks),
            "claims": len(state.validated_claims),
        }),
        started_at=started,
    )
    db.add(task)
    db.commit()

    try:
        language_instruction = ""
        if state.language and state.language != "English":
            language_instruction = f"\n- IMPORTANT: Write the ENTIRE report in {state.language}. All headings, content, and analysis must be in {state.language}.\n"

        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a senior research writer. Write a comprehensive, well-structured "
                "research report in markdown format. Requirements:\n"
                "- Use ## for section headers\n"
                "- Cite sources inline as [1], [2], etc. matching the numbered excerpts\n"
                "- Include: Executive Summary, Key Findings, Detailed Analysis, "
                "  Contradictions/Gaps (if any), Conclusion, References\n"
                "- Be factual, concise, and objective\n"
                "- Length: 600-900 words"
                + language_instruction
            )),
            HumanMessage(content=_build_writer_prompt(state)),
        ])

        report = response.content.strip()

        # Append references section
        unique_urls = list(dict.fromkeys(c.url for c in state.chunks))
        refs = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(unique_urls[:12]))
        if "## References" not in report:
            report += f"\n\n## References\n{refs}"

        # Persist report to DB
        finished = datetime.datetime.utcnow()
        job = db.query(ResearchJob).filter(ResearchJob.id == state.job_id).first()
        if job:
            job.status = "done"
            job.report = report
            job.finished_at = finished

        task.status = "done"
        task.output_data = json.dumps({"report_length": len(report)})
        task.finished_at = finished
        task.duration_ms = (finished - started).total_seconds() * 1000
        db.commit()

        # Send email notification to user
        if job and job.user_id:
            user = db.query(User).filter(User.id == job.user_id).first()
            if user and user.email:
                try:
                    from shared.auth import send_report_notification
                    import asyncio
                    asyncio.ensure_future(send_report_notification(user.email, state.query, state.job_id, user_id=job.user_id))
                except Exception as notify_err:
                    logger.warning(f"[writer_agent] Notification failed: {notify_err}")

        logger.info(f"[writer_agent] Report generated ({len(report)} chars)")
        return {
            "report": report,
            "completed_agents": ["writer"],
        }

    except Exception as e:
        task.status = "failed"
        job = db.query(ResearchJob).filter(ResearchJob.id == state.job_id).first()
        if job:
            job.status = "failed"
        db.commit()
        logger.error(f"[writer_agent] Error: {e}")
        return {"errors": [f"writer_agent: {str(e)}"]}

    finally:
        db.close()
