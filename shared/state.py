"""
Shared data models and the LangGraph pipeline state.

Defines the Pydantic models exchanged between agents (search results, extracted
chunks, validated claims) and the `ResearchState` object that flows through the
LangGraph state machine, accumulating each agent's output as the pipeline runs.
"""
from __future__ import annotations
from typing import Annotated, Any
from pydantic import BaseModel, Field
from datetime import datetime
import operator


# ── Shared data models ────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """A single source discovered by the search agent (web page or paper)."""
    url: str
    title: str
    snippet: str
    source_type: str = "web"  # web | arxiv | pdf


class ExtractedChunk(BaseModel):
    """A relevance-scored passage of text extracted from a source."""
    url: str
    content: str
    relevance_score: float = 0.0
    source_type: str = "web"


class ValidatedClaim(BaseModel):
    """A claim fact-checked against sources, with supporting/contradicting URLs."""
    claim: str
    supported_by: list[str]   # list of URLs
    contradicted_by: list[str] = []
    confidence: float = 1.0


# ── LangGraph pipeline state ──────────────────────────────────────────────────
# Annotated[list, operator.add] means each agent *appends* to the list
# rather than overwriting it — safe for parallel agent execution.

class ResearchState(BaseModel):
    """
    The mutable state threaded through the LangGraph research pipeline.

    Each agent reads the fields it needs and returns a partial update; list
    fields are merged via `operator.add` (append) so that updates from
    sequential — or potentially parallel — agents accumulate instead of
    clobbering one another.
    """
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
