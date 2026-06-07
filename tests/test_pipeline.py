"""
Run with: pytest tests/ -v
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from shared.state import ResearchState, SearchResult, ExtractedChunk, ValidatedClaim
from shared.message_bus import MessageBus


# ── MessageBus ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_bus_publish_consume():
    bus = MessageBus()
    await bus.publish("test", "hello")
    msg = await bus.consume("test")
    assert msg == "hello"


@pytest.mark.asyncio
async def test_message_bus_consume_nowait_empty():
    bus = MessageBus()
    result = await bus.consume_nowait("empty_channel")
    assert result is None


@pytest.mark.asyncio
async def test_message_bus_multiple_channels():
    bus = MessageBus()
    await bus.publish("ch1", "a")
    await bus.publish("ch2", "b")
    assert await bus.consume("ch1") == "a"
    assert await bus.consume("ch2") == "b"


# ── ResearchState ─────────────────────────────────────────────────────────────

def test_state_initializes_empty():
    state = ResearchState(job_id="abc", query="test query")
    assert state.query == "test query"
    assert state.search_results == []
    assert state.chunks == []
    assert state.report == ""


def test_state_list_merging():
    """Annotated[list, operator.add] means dicts get merged via addition."""
    import operator
    a = [SearchResult(url="http://a.com", title="A", snippet="a")]
    b = [SearchResult(url="http://b.com", title="B", snippet="b")]
    merged = operator.add(a, b)
    assert len(merged) == 2


# ── Search agent ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_agent_returns_results():
    mock_results = [
        SearchResult(url="https://example.com", title="Example", snippet="Test content"),
    ]

    with patch("agents.search_agent.client") as mock_client, \
         patch("agents.search_agent._run_web_search", return_value=mock_results), \
         patch("agents.search_agent.SessionLocal") as mock_db:

        # Mock DB session
        mock_session = MagicMock()
        mock_db.return_value = mock_session

        # Mock OpenAI response (no tool calls = agent done after one round)
        mock_msg = MagicMock()
        mock_msg.tool_calls = None
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_msg)]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        from agents.search_agent import search_agent
        state = ResearchState(job_id="test-123", query="quantum computing")
        result = await search_agent(state)

        assert "completed_agents" in result
        assert "search" in result["completed_agents"]


# ── Extractor agent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extractor_agent_skips_empty_content():
    with patch("agents.extractor_agent._fetch_content", return_value=""), \
         patch("agents.extractor_agent.SessionLocal") as mock_db:

        mock_db.return_value = MagicMock()

        from agents.extractor_agent import extractor_agent
        state = ResearchState(
            job_id="test-456",
            query="test",
            search_results=[
                SearchResult(url="https://empty.com", title="Empty", snippet="")
            ],
        )
        result = await extractor_agent(state)
        assert result.get("chunks", []) == [] or "errors" in result


# ── Validator agent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validator_handles_no_chunks():
    with patch("agents.validator_agent.SessionLocal") as mock_db:
        mock_db.return_value = MagicMock()

        from agents.validator_agent import validator_agent
        state = ResearchState(job_id="test-789", query="test", chunks=[])
        result = await validator_agent(state)
        # Should not crash — may return empty claims or an error
        assert isinstance(result, dict)


# ── Orchestrator routing ──────────────────────────────────────────────────────

def test_routing_no_results_goes_to_end():
    from agents.orchestrator import should_continue_after_search
    state = ResearchState(job_id="x", query="q", search_results=[])
    assert should_continue_after_search(state) == "end"


def test_routing_with_results_goes_to_extractor():
    from agents.orchestrator import should_continue_after_search
    state = ResearchState(
        job_id="x",
        query="q",
        search_results=[SearchResult(url="http://a.com", title="A", snippet="a")],
    )
    assert should_continue_after_search(state) == "extractor"


def test_routing_no_chunks_skips_to_writer():
    from agents.orchestrator import should_continue_after_extraction
    state = ResearchState(job_id="x", query="q", chunks=[])
    assert should_continue_after_extraction(state) == "writer"


def test_routing_with_chunks_goes_to_validator():
    from agents.orchestrator import should_continue_after_extraction
    state = ResearchState(
        job_id="x",
        query="q",
        chunks=[ExtractedChunk(url="http://a.com", content="chunk", relevance_score=0.8)],
    )
    assert should_continue_after_extraction(state) == "validator"
