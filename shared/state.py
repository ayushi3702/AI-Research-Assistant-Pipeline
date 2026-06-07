from __future__ import annotations
from typing import Annotated, Any
from pydantic import BaseModel, Field
from datetime import datetime
import operator


# ── Shared data models ────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    source_type: str = "web"  # web | arxiv | pdf


class ExtractedChunk(BaseModel):
    url: str
    content: str
    relevance_score: float = 0.0
    source_type: str = "web"


class ValidatedClaim(BaseModel):
    claim: str
    supported_by: list[str]   # list of URLs
    contradicted_by: list[str] = []
    confidence: float = 1.0


# ── LangGraph pipeline state ──────────────────────────────────────────────────
# Annotated[list, operator.add] means each agent *appends* to the list
# rather than overwriting it — safe for parallel agent execution.

class ResearchState(BaseModel):
    # Input
    job_id: str = ""
    query: str = ""
    language: str = "English"

    # Search agent output
    search_results: Annotated[list[SearchResult], operator.add] = Field(default_factory=list)

    # Extractor agent output
    chunks: Annotated[list[ExtractedChunk], operator.add] = Field(default_factory=list)

    # Validator agent output
    validated_claims: Annotated[list[ValidatedClaim], operator.add] = Field(default_factory=list)

    # RAG agent output — relevant context from past research
    rag_context: Annotated[list[dict], operator.add] = Field(default_factory=list)

    # Writer agent output
    report: str = ""

    # Orchestrator bookkeeping
    current_agent: str = "orchestrator"
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)
    completed_agents: Annotated[list[str], operator.add] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
