"""
System 1 Hot-Path Pipeline
===========================
Fully async, non-blocking event processing pipeline.

Latency budget: <50ms per event.
Hydration → Feature Extraction → ML Classification → Governance → Dispatch → Ledger.

All I/O (Redis, PostgreSQL, OPA) runs asynchronously.
CPU-bound ML inference is offloaded to thread pool via asyncio.to_thread.
"""

import asyncio

from loguru import logger

from src.execution.dispatcher import ActionDispatcher
from src.execution.suppressor import ActionSuppressor
from src.governance.opa_client import OPAClient
from src.memory import get_event_store, get_session_store
from src.models.actions import ActionDispatch
from src.models.events import ClickEvent
from src.models.features import SessionFeatures
from src.perception.feature_engineer import FeatureEngineer
from src.reasoning.markov_model import MarkovIntentModel
from src.reasoning.ml_ensemble import MLEnsembleClassifier
from src.reasoning.slm_enrichment import get_slm_enrichment

# Singleton instances — lazily initialized
_dispatcher: ActionDispatcher | None = None
_suppressor: ActionSuppressor | None = None
_engineer: FeatureEngineer | None = None
_classifier: MLEnsembleClassifier | None = None
_markov: MarkovIntentModel | None = None
_opa: OPAClient | None = None


def _get_dispatcher() -> ActionDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ActionDispatcher()
    return _dispatcher


def _get_suppressor() -> ActionSuppressor:
    global _suppressor
    if _suppressor is None:
        _suppressor = ActionSuppressor()
    return _suppressor


def _get_engineer() -> FeatureEngineer:
    global _engineer
    if _engineer is None:
        _engineer = FeatureEngineer()
    return _engineer


def _get_classifier() -> MLEnsembleClassifier:
    global _classifier
    if _classifier is None:
        _classifier = MLEnsembleClassifier()
    return _classifier


def _get_markov() -> MarkovIntentModel:
    global _markov
    if _markov is None:
        _markov = MarkovIntentModel()
    return _markov


def _get_opa() -> OPAClient:
    global _opa
    if _opa is None:
        _opa = OPAClient()
    return _opa



async def _hydrate_state(
    session_id: str,
) -> tuple[dict | None, list[ClickEvent], dict | None]:
    """Hydrate session state, events, and customer profile in parallel."""
    session_store = get_session_store()
    event_store = get_event_store()

    session_task = session_store.get(session_id)
    events_task = event_store.get_session_events(session_id)

    session, events = await asyncio.gather(session_task, events_task)

    customer = None
    if session and session.get("customer_id"):
        # Customer profile hydration would go here (future Redis hash lookup)
        customer = {"customer_id": session["customer_id"]}

    return session, events, customer


async def _run_classification(features: SessionFeatures) -> tuple[str, float, str]:
    """Run ML ensemble classification offloaded to thread pool (CPU-bound)."""
    classifier = _get_classifier()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, classifier.classify, features)


async def _run_governance(
    action: str,
    customer: dict | None,
    features: SessionFeatures,
    intent: str = "",
) -> tuple[bool, str]:
    """Evaluate governance via OPA (async HTTP). Fail-closed on errors."""
    opa = _get_opa()
    allowed = await opa.evaluate(
        action=action,
        intent=intent,
        customer=customer or {},
        features=features.model_dump(),
    )
    return allowed, ""


async def process_event(event: ClickEvent) -> ActionDispatch:
    """
    System 1 hot-path: process a single click event end-to-end.

    Pipeline stages (all async):
    1. Hydrate session state from Redis/SQLite
    2. Engineer features from session events
    3. Classify intent via ML ensemble (offloaded to thread)
    4. Evaluate governance via OPA
    5. Dispatch action
    6. Log to PostgreSQL ledger

    Returns ActionDispatch with the chosen action.
    """
    session_id = event.session_id

    # Stage 1: Parallel state hydration
    session, events, customer = await _hydrate_state(session_id)

    # Stage 2: Feature engineering (CPU-bound, but fast with Polars)
    engineer = _get_engineer()
    features = engineer.engineer(events)

    # Stage 3: ML classification + optional SLM enrichment in parallel
    slm = get_slm_enrichment()
    ml_task = _run_classification(features)
    slm_task = slm.enrich_intent(features.model_dump()) if slm.available else asyncio.sleep(0, result=None)
    intent, confidence, method = await ml_task
    slm_result = await slm_task

    # If SLM enrichment is available and ML confidence is low, prefer SLM
    if slm_result and slm_result["confidence"] > confidence:
        intent = slm_result["intent"]
        confidence = slm_result["confidence"]
        method = "slm_enrichment"

    # Stage 4: Governance evaluation (async OPA)
    action_dispatch_obj = _get_dispatcher()
    action_map = action_dispatch_obj.ACTION_MAP
    proposed_action = action_map.get(intent, "NO_ACTION")

    allowed, reason = await _run_governance(proposed_action, customer, features, intent=intent)

    # Stage 5: Action dispatch with suppression
    suppressor = _get_suppressor()
    if not suppressor.can_dispatch(session_id, proposed_action):
        dispatch = ActionDispatch(
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            action="NO_ACTION",
            reason="SUPPRESSED_WITHIN_15MIN",
        )
    elif not allowed:
        dispatch = ActionDispatch(
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            action="NO_ACTION",
            reason=reason,
        )
    else:
        dispatch = ActionDispatcher().dispatch(
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            features=features,
            governance_allowed=allowed,
            governance_reason=reason,
        )

    # Stage 6: Log to ledger (non-blocking, fire-and-forget with error handling)
    try:
        from src.execution import get_action_ledger

        ledger = get_action_ledger()
        await ledger.record(dispatch)
    except Exception as e:
        logger.error(f"Failed to log action to ledger: {e}")

    # Record suppression timestamp if action was dispatched
    if dispatch.action != "NO_ACTION":
        suppressor.record(session_id, dispatch.action)

    return dispatch


async def ingest_event(event: ClickEvent) -> None:
    """
    Ingest a click event into the hot memory stores.

    Writes to both session store and event store asynchronously.
    """
    session_store = get_session_store()
    event_store = get_event_store()

    await asyncio.gather(
        session_store.upsert(event.session_id, event.customer_id),
        event_store.insert(event),
    )


async def close_pipeline() -> None:
    """Gracefully close all pipeline resources."""
    global _opa
    from src.execution import close_ledger
    from src.memory import close_stores
    from src.reasoning.slm_enrichment import close_slm

    await asyncio.gather(
        close_stores(),
        close_ledger(),
        close_slm(),
        _opa.close() if _opa else asyncio.sleep(0),
        return_exceptions=True,
    )
    _opa = None
    logger.info("Pipeline resources closed")
