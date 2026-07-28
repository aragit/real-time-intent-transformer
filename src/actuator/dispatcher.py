"""
Action Dispatcher (Closed-Loop Executor)
========================================
Listens to pipeline output (ActionDispatch) and executes the final action:

- **ALLOWED**  → log and execute the mock API call.
- **DENIED**   → log the block and route the failure into the episodic
  memory ledger so the system retains a vector trace of the blocked
  hallucination for downstream meta-cognition.
"""

from loguru import logger

from src.memory.qdrant_ledger import QdrantEpisodicMemory, get_episodic_memory
from src.models.actions import ActionDispatch

_VERDICT_ALLOWED = "ALLOWED"
_VERDICT_DENIED = "DENIED"

_ACTION_HANDLERS: dict[str, str] = {
    "RECOMMEND_ALTERNATIVE": "Mock catalog recommendation API",
    "SHOW_COMPARISON_TOOL": "Mock comparison widget renderer",
    "APPLY_DISCOUNT": "Mock discount-code issuance endpoint",
    "SHOW_URGENCY": "Mock urgency banner API",
    "SEND_ABANDON_EMAIL": "Mock email campaign trigger",
    "LOYALTY_REWARD": "Mock loyalty-points accrual API",
    "LOG_ANALYTICS": "Mock analytics event emitter",
}


class ClosedLoopDispatcher:
    """Routes ActionDispatch results through execution or memory storage."""

    def __init__(
        self,
        episodic_memory: QdrantEpisodicMemory | None = None,
    ):
        self._memory = episodic_memory

    def _resolve_memory(self) -> QdrantEpisodicMemory:
        if self._memory is not None:
            return self._memory
        return get_episodic_memory()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        dispatch: ActionDispatch,
        opa_verdict: str = _VERDICT_ALLOWED,
    ) -> str:
        """Process a completed ActionDispatch.

        Parameters
        ----------
        dispatch:
            The ActionDispatch produced by the pipeline.
        opa_verdict:
            ``"ALLOWED"`` or ``"DENIED"`` — mirrors the governance result.

        Returns
        -------
        str
            A human-readable summary of what happened.
        """
        if opa_verdict == _VERDICT_ALLOWED:
            return await self._execute_allowed(dispatch)
        return await self._handle_denied(dispatch, opa_verdict)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _execute_allowed(self, dispatch: ActionDispatch) -> str:
        handler_desc = _ACTION_HANDLERS.get(dispatch.action, dispatch.action)
        logger.info(
            f"Executing mock API call for {dispatch.action} "
            f"(session={dispatch.session_id}, intent={dispatch.intent}, "
            f"confidence={dispatch.confidence:.2f}) — {handler_desc}"
        )
        return f"EXECUTED:{dispatch.action}"

    async def _handle_denied(
        self, dispatch: ActionDispatch, opa_verdict: str
    ) -> str:
        logger.warning(
            f"Action BLOCKED by governance: {dispatch.action} "
            f"(session={dispatch.session_id}, intent={dispatch.intent}, "
            f"confidence={dispatch.confidence:.2f}) — reason={dispatch.reason}"
        )
        memory = self._resolve_memory()
        try:
            await memory.store_decision(
                session_id=dispatch.session_id,
                intent=dispatch.intent,
                proposed_action=dispatch.action,
                opa_verdict=opa_verdict,
            )
        except Exception:
            logger.error(
                f"Failed to store denied action in episodic memory "
                f"(session={dispatch.session_id}): "
                f"{__import__('traceback').format_exc()}"
            )
        return f"DENIED:{dispatch.action}"
