"""
Closed-Loop Tests
=================
Isolated pytest unit tests for the episodic memory ledger and the
closed-loop action dispatcher.

All external I/O (Qdrant, Ollama) is replaced with AsyncMock so the
tests are fast, hermetic, and deterministic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.actuator.dispatcher import _VERDICT_ALLOWED, _VERDICT_DENIED, ClosedLoopDispatcher
from src.memory.qdrant_ledger import (
    COLLECTION_NAME,
    EMBEDDING_DIM,
    QdrantEpisodicMemory,
    _build_summary,
)
from src.models.actions import ActionDispatch

MOCK_VECTOR = [0.1] * EMBEDDING_DIM


def _make_mock_memory() -> QdrantEpisodicMemory:
    """Build a QdrantEpisodicMemory with fully mocked internals."""
    mem = QdrantEpisodicMemory()
    mem._client = MagicMock()
    # Patch _embed so we never hit real Ollama.
    mem._embed = AsyncMock(return_value=MOCK_VECTOR)
    return mem


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def allowed_dispatch() -> ActionDispatch:
    return ActionDispatch(
        session_id="sess_test_001",
        intent="BROWSE",
        confidence=0.87,
        action="RECOMMEND_ALTERNATIVE",
        reason=None,
    )


@pytest.fixture
def denied_dispatch() -> ActionDispatch:
    return ActionDispatch(
        session_id="sess_test_002",
        intent="PRICE_SENSITIVE",
        confidence=0.63,
        action="APPLY_DISCOUNT",
        reason="FAIL_CLOSED_OPA_UNREACHABLE",
    )


@pytest.fixture
def mock_episodic_memory() -> QdrantEpisodicMemory:
    return _make_mock_memory()


@pytest.fixture
def dispatcher(mock_episodic_memory: QdrantEpisodicMemory) -> ClosedLoopDispatcher:
    return ClosedLoopDispatcher(episodic_memory=mock_episodic_memory)


# ──────────────────────────────────────────────────────────────────────
# QdrantEpisodicMemory unit tests
# ──────────────────────────────────────────────────────────────────────


class TestQdrantEpisodicMemory:

    def test_build_summary(self):
        summary = _build_summary("s1", "BROWSE", "RECOMMEND_ALTERNATIVE", "ALLOWED")
        assert summary == (
            "User exhibited BROWSE intent. "
            "SLM proposed RECOMMEND_ALTERNATIVE. "
            "OPA verdict: ALLOWED."
        )

    def test_build_summary_denied(self):
        summary = _build_summary("s2", "CHURN_RISK", "ISSUE_DISCOUNT", "DENIED")
        assert "DENIED" in summary
        assert "ISSUE_DISCOUNT" in summary

    @pytest.mark.asyncio
    async def test_embed_calls_ollama(self):
        """_embed hits the Ollama /api/embed endpoint and returns a vector."""
        mem = QdrantEpisodicMemory()
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embeddings": [MOCK_VECTOR]}
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch.object(mem, "_get_http", return_value=mock_http):
            vector = await mem._embed("test text")

        assert len(vector) == EMBEDDING_DIM
        mock_http.post.assert_called_once()
        url = mock_http.post.call_args[0][0]
        assert url.endswith("/api/embed")

    @pytest.mark.asyncio
    async def test_store_decision_upserts_to_qdrant(
        self, mock_episodic_memory: QdrantEpisodicMemory
    ):
        point_id = await mock_episodic_memory.store_decision(
            session_id="s1",
            intent="BROWSE",
            proposed_action="RECOMMEND_ALTERNATIVE",
            opa_verdict="ALLOWED",
        )

        assert isinstance(point_id, str)
        assert len(point_id) == 36  # UUID4 format
        mock_episodic_memory._client.upsert.assert_called_once()
        call_kwargs = mock_episodic_memory._client.upsert.call_args
        assert call_kwargs[1]["collection_name"] == COLLECTION_NAME

        point = call_kwargs[1]["points"][0]
        assert point.payload["session_id"] == "s1"
        assert point.payload["intent"] == "BROWSE"
        assert point.payload["proposed_action"] == "RECOMMEND_ALTERNATIVE"
        assert point.payload["opa_verdict"] == "ALLOWED"
        assert len(point.vector) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_store_decision_denied_stores_verdict(
        self, mock_episodic_memory: QdrantEpisodicMemory
    ):
        point_id = await mock_episodic_memory.store_decision(
            session_id="s2",
            intent="CHURN_RISK",
            proposed_action="ISSUE_DISCOUNT",
            opa_verdict="DENIED",
        )

        assert isinstance(point_id, str)
        call_kwargs = mock_episodic_memory._client.upsert.call_args
        point = call_kwargs[1]["points"][0]
        assert point.payload["opa_verdict"] == "DENIED"
        assert point.payload["proposed_action"] == "ISSUE_DISCOUNT"

    @pytest.mark.asyncio
    async def test_embed_failure_propagates(self):
        """If Ollama is unreachable, _embed should raise."""
        mem = QdrantEpisodicMemory()
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("connection refused")
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch.object(mem, "_get_http", return_value=mock_http):
            with pytest.raises(Exception, match="connection refused"):
                await mem._embed("test")


# ──────────────────────────────────────────────────────────────────────
# ClosedLoopDispatcher unit tests
# ──────────────────────────────────────────────────────────────────────


class TestClosedLoopDispatcher:

    @pytest.mark.asyncio
    async def test_allowed_action_executes(
        self,
        dispatcher: ClosedLoopDispatcher,
        allowed_dispatch: ActionDispatch,
    ):
        result = await dispatcher.dispatch(
            allowed_dispatch, opa_verdict=_VERDICT_ALLOWED
        )

        assert result == "EXECUTED:RECOMMEND_ALTERNATIVE"

    @pytest.mark.asyncio
    async def test_denied_action_logs_and_stores(
        self,
        dispatcher: ClosedLoopDispatcher,
        denied_dispatch: ActionDispatch,
    ):
        result = await dispatcher.dispatch(
            denied_dispatch, opa_verdict=_VERDICT_DENIED
        )

        assert result == "DENIED:APPLY_DISCOUNT"
        dispatcher._memory._client.upsert.assert_called_once()
        call_kwargs = dispatcher._memory._client.upsert.call_args
        point = call_kwargs[1]["points"][0]
        assert point.payload["opa_verdict"] == "DENIED"
        assert point.payload["proposed_action"] == "APPLY_DISCOUNT"
        assert point.payload["session_id"] == "sess_test_002"

    @pytest.mark.asyncio
    async def test_denied_action_does_not_crash_on_memory_failure(
        self,
        denied_dispatch: ActionDispatch,
    ):
        failing_memory = QdrantEpisodicMemory()
        failing_memory._client = MagicMock()
        failing_memory._client.upsert.side_effect = ConnectionError("Qdrant down")
        failing_memory._embed = AsyncMock(return_value=MOCK_VECTOR)

        dispatcher = ClosedLoopDispatcher(episodic_memory=failing_memory)
        result = await dispatcher.dispatch(
            denied_dispatch, opa_verdict=_VERDICT_DENIED
        )

        assert result == "DENIED:APPLY_DISCOUNT"

    @pytest.mark.asyncio
    async def test_unknown_action_allowed(
        self,
        mock_episodic_memory: QdrantEpisodicMemory,
    ):
        dispatch = ActionDispatch(
            session_id="sess_x",
            intent="UNKNOWN",
            confidence=0.5,
            action="LOG_ANALYTICS",
        )
        dispatcher = ClosedLoopDispatcher(episodic_memory=mock_episodic_memory)
        result = await dispatcher.dispatch(dispatch, opa_verdict=_VERDICT_ALLOWED)

        assert result == "EXECUTED:LOG_ANALYTICS"

    @pytest.mark.asyncio
    async def test_allowed_does_not_touch_memory(
        self,
        dispatcher: ClosedLoopDispatcher,
        allowed_dispatch: ActionDispatch,
    ):
        await dispatcher.dispatch(allowed_dispatch, opa_verdict=_VERDICT_ALLOWED)

        dispatcher._memory._client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_verdict_routing_completes_end_to_end(
        self,
        dispatcher: ClosedLoopDispatcher,
    ):
        dispatch = ActionDispatch(
            session_id="sess_end_to_end",
            intent="CHECKOUT_INTENT",
            confidence=0.91,
            action="SHOW_URGENCY",
            reason="GOVERNANCE_DENY",
        )
        result = await dispatcher.dispatch(
            dispatch, opa_verdict=_VERDICT_DENIED
        )

        assert result == "DENIED:SHOW_URGENCY"
        call_kwargs = dispatcher._memory._client.upsert.call_args
        point = call_kwargs[1]["points"][0]
        assert point.payload["session_id"] == "sess_end_to_end"
        assert point.payload["intent"] == "CHECKOUT_INTENT"
        assert point.payload["proposed_action"] == "SHOW_URGENCY"
        assert point.payload["opa_verdict"] == "DENIED"
