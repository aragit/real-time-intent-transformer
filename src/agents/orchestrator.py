"""
Agentic Orchestrator (Phase 2)
==============================
LangGraph StateGraph for dual-path routing:
  - System 1: Fast path (existing pipeline, <50ms)
  - System 2: Agentic path (LLM + GraphRAG + Critic, unlimited latency)

The orchestrator inspects incoming events and routes them to the appropriate
system based on confidence thresholds and complexity signals.

System 2 includes a Critic Agent that validates the Planner's proposed action
against deterministic OPA policies before final dispatch.
"""

from typing import TypedDict, Literal, Optional
from loguru import logger

from langgraph.graph import StateGraph, END

from src.config import settings


class OrchestratorState(TypedDict):
    """State passed through the graph nodes."""
    session_id: str
    customer_id: Optional[str]
    event_type: str
    intent: Optional[str]
    confidence: Optional[float]
    recent_events: list[dict]
    features: dict
    system: Optional[Literal["system_1", "system_2"]]
    result: Optional[dict]
    proposed_action: Optional[str]
    opa_evaluation: Optional[dict]
    final_action: Optional[dict]


async def system_1_fast_path(state: OrchestratorState) -> OrchestratorState:
    """
    System 1: Deterministic, sub-50ms fast path.
    Runs existing ML ensemble + rule-based classification.
    """
    from src.pipeline import process_event
    from src.models.events import ClickEvent

    logger.debug(f"System 1 fast path for session {state['session_id']}")

    event = ClickEvent(
        session_id=state["session_id"],
        customer_id=state.get("customer_id"),
        action=state.get("event_type", "page_view"),
    )
    dispatch = await process_event(event)

    return {
        **state,
        "system": "system_1",
        "result": {
            "action": dispatch.action,
            "intent": dispatch.intent,
            "confidence": dispatch.confidence,
            "reason": dispatch.reason,
            "source": "system_1",
        },
    }


async def system_2_agentic_path(state: OrchestratorState) -> OrchestratorState:
    """
    System 2: LLM-powered agentic path with GraphRAG.
    Used for complex intents, ambiguous signals, or multi-step reasoning.

    The Planner Agent proposes an action, which is stored in proposed_action
    for the Critic Agent to validate against OPA policies.
    """
    from src.agents.planner import run_planner

    logger.info(
        f"System 2 agentic path for session {state['session_id']} "
        f"(confidence={state.get('confidence', 0):.2f}, intent={state.get('intent')})"
    )

    planner_result = await run_planner(
        session_id=state["session_id"],
        customer_id=state.get("customer_id"),
        intent=state.get("intent", "UNKNOWN"),
        confidence=state.get("confidence", 0.0),
        recent_events=state.get("recent_events", []),
        features=state.get("features", {}),
    )

    proposed_action = planner_result.get("action", "NO_ACTION")
    logger.info(
        f"Planner proposed '{proposed_action}' for session {state['session_id']}"
    )

    return {
        **state,
        "system": "system_2",
        "result": planner_result,
        "proposed_action": proposed_action,
    }


async def critic_node(state: OrchestratorState) -> OrchestratorState:
    """
    Critic Agent: validates the Planner's proposed action against OPA policies.

    - If OPA allows → approve unchanged
    - If OPA denies → rewrite to compliant fallback via LLM
    - If rewrite fails → hard NO_ACTION

    System 1 bypasses this node entirely to maintain sub-50ms latency.
    """
    from src.agents.critic import run_critic

    proposed = state.get("proposed_action", "NO_ACTION")
    result = state.get("result", {})

    logger.info(
        f"Critic evaluating '{proposed}' for session {state['session_id']}"
    )

    evaluation = await run_critic(
        proposed_action=proposed,
        session_id=state["session_id"],
        customer_id=state.get("customer_id"),
        confidence=result.get("confidence", 0.0),
        reasoning=result.get("reasoning", ""),
        product_context=result.get("product_context", ""),
        customer_segment=result.get("customer_segment", "unknown"),
        features=state.get("features", {}),
    )

    final_result = {
        "action": evaluation["action"],
        "intent": result.get("intent", state.get("intent", "UNKNOWN")),
        "confidence": result.get("confidence", 0.0),
        "reason": evaluation["reasoning"],
        "source": evaluation["source"],
        "original_proposed": proposed,
    }

    logger.info(
        f"Critic result for session {state['session_id']}: "
        f"'{proposed}' → '{evaluation['action']}' "
        f"(OPA allowed={evaluation['opa_allowed']}, source={evaluation['source']})"
    )

    return {
        **state,
        "opa_evaluation": {
            "allowed": evaluation["opa_allowed"],
            "proposed_action": proposed,
        },
        "final_action": final_result,
        "result": final_result,
    }


def route_by_complexity(state: OrchestratorState) -> str:
    """
    Routing function: determines System 1 vs System 2.

    Routes to System 2 if:
    - ML confidence is below the configurable threshold (default 0.70)
    - Intent is complex (CHURN_RISK, LOYAL_RETURNER)
    - Session shows high exploration ratio (ambiguous behavior)
    """
    confidence = state.get("confidence")
    intent = state.get("intent")
    features = state.get("features", {})

    threshold = settings.system_2_confidence_threshold

    if confidence is not None and confidence < threshold:
        logger.info(
            f"Low confidence ({confidence:.2f} < {threshold}) → System 2 "
            f"for session {state['session_id']}"
        )
        return "system_2"

    if intent in ("CHURN_RISK", "LOYAL_RETURNER"):
        logger.info(
            f"Complex intent ({intent}) → System 2 "
            f"for session {state['session_id']}"
        )
        return "system_2"

    exploration = features.get("exploration_ratio", 0.0)
    if exploration > 0.6:
        logger.info(
            f"High exploration ({exploration:.2f}) → System 2 "
            f"for session {state['session_id']}"
        )
        return "system_2"

    return "system_1"


def build_orchestrator_graph() -> StateGraph:
    """
    Build the LangGraph StateGraph for the orchestrator.

    Graph structure:
        START → route_by_complexity → system_1_fast_path → END
                                    → system_2_agentic_path → critic_node → END
    """
    graph = StateGraph(OrchestratorState)

    # Add nodes
    graph.add_node("system_1_fast_path", system_1_fast_path)
    graph.add_node("system_2_agentic_path", system_2_agentic_path)
    graph.add_node("critic_node", critic_node)

    # Set entry point with conditional routing
    graph.set_conditional_entry_point(
        route_by_complexity,
        {
            "system_1": "system_1_fast_path",
            "system_2": "system_2_agentic_path",
        },
    )

    # System 1 bypasses the Critic for sub-50ms latency
    graph.add_edge("system_1_fast_path", END)

    # System 2 must pass through the Critic before final dispatch
    graph.add_edge("system_2_agentic_path", "critic_node")
    graph.add_edge("critic_node", END)

    return graph.compile()


# Singleton compiled graph
_graph = None


def get_orchestrator():
    """Get the compiled orchestrator graph (lazy singleton)."""
    global _graph
    if _graph is None:
        _graph = build_orchestrator_graph()
    return _graph
