"""
Critic Agent (LLM Verifier & Deterministic Governance)
=======================================================
Intercepts the Planner Agent's proposed action and validates it against
deterministic OPA policies before final dispatch.

The Critic acts as a hard gate in the System 2 agentic path:
  1. Evaluate proposed action via OPA
  2. If allowed -> approve unchanged
  3. If denied -> rewrite to compliant fallback using local LLM
  4. If rewrite fails -> hard NO_ACTION with denial reason

This ensures the LLM Planner cannot bypass business policy constraints
(e.g., discount limits, restricted items, rate limits).
"""

import asyncio
import re

from loguru import logger

from src.config import settings
from src.governance.opa_client import OPAClient

CRITIC_LLM_TIMEOUT_SECONDS = 15.0


# Lazy-initialized LLM for fallback rewriting
_llm = None


def _strip_v1_suffix(url: str) -> str:
    """Strip /v1 suffix from a URL using proper URL parsing."""
    from urllib.parse import urlparse, urlunsplit

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit(parsed._replace(path=path))


def _get_llm():
    """Get or create the LLM client for fallback rewriting."""
    global _llm
    if _llm is None:
        if settings.llm_provider == "ollama":
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from langchain_community.chat_models import ChatOllama

            _llm = ChatOllama(
                model=settings.llm_model,
                base_url=_strip_v1_suffix(settings.llm_base_url),
            )
        else:
            from langchain_openai import ChatOpenAI

            _llm = ChatOpenAI(
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                temperature=0.1,
                max_tokens=256,
            )
        logger.info(f"Critic LLM initialized: {settings.llm_provider}/{settings.llm_model}")
    return _llm


CRITIC_SYSTEM_PROMPT = """You are a compliance critic for an e-commerce intervention system.

Your job is to rewrite a non-compliant action into a policy-compliant alternative.

## Rules
- You must output ONLY a JSON object, no other text.
- The rewritten action must use one of: NO_ACTION, SHOW_URGENCY, SEND_ABANDON_EMAIL, OFFER_BUNDLE, SEND_TO_HUMAN, LOYALTY_REWARD, RECOMMEND_ALTERNATIVE
- You CANNOT use APPLY_DISCOUNT or OFFER_DISCOUNT if OPA denied them.
- Prefer the safest fallback: NO_ACTION or SEND_TO_HUMAN for ambiguous cases.

## Input
- Original action: the action that was denied by policy
- OPA denial reason: why it was denied
- Customer context: customer tier, history, cart value

## Output Format
{"action": "<COMPLIANT_ACTION>", "reasoning": "<why this fallback>"}
"""


async def run_critic(
    proposed_action: str,
    session_id: str,
    customer_id: str | None,
    confidence: float,
    reasoning: str,
    product_context: str,
    customer_segment: str,
    features: dict,
    opa_client: OPAClient | None = None,
) -> dict:
    """
    Evaluate a proposed action against OPA policies and rewrite if necessary.

    Args:
        proposed_action: The action recommended by the Planner Agent.
        session_id: Session identifier for logging context.
        customer_id: Customer identifier (may be None for anonymous).
        confidence: Planner's confidence score.
        reasoning: Planner's reasoning for the proposed action.
        product_context: Product graph context from the Planner.
        customer_segment: Identified customer segment.
        features: Session features for OPA evaluation.
        opa_client: Optional OPA client instance (uses singleton if None).

    Returns:
        Dict with keys: action, reasoning, source, opa_allowed.
    """
    if opa_client is None:
        opa_client = OPAClient()

    customer = {"customer_id": customer_id} if customer_id else {}

    # Step 1: Evaluate against OPA
    try:
        opa_allowed = await opa_client.evaluate(
            action=proposed_action,
            intent=features.get("intent", ""),
            discount_value=features.get("discount_value", 0.0),
            customer=customer,
            features=features,
        )
    except Exception as e:
        logger.warning(f"OPA evaluation failed for critic: {e}. Denying action.")
        opa_allowed = False

    if opa_allowed:
        logger.info(f"Critic approved '{proposed_action}' for session {session_id} (OPA allowed)")
        return {
            "action": proposed_action,
            "reasoning": reasoning,
            "source": "system_2_critic_approved",
            "opa_allowed": True,
        }

    # Step 2: OPA denied — attempt LLM rewrite to compliant fallback
    logger.info(
        f"Critic: OPA denied '{proposed_action}' for session {session_id}. "
        f"Attempting compliant rewrite."
    )

    try:
        llm = _get_llm()
        from langchain_core.messages import HumanMessage, SystemMessage

        rewrite_prompt = (
            f"Original action: {proposed_action}\n"
            f"OPA denial reason: Policy evaluation returned allowed=false\n"
            f"Customer ID: {customer_id or 'anonymous'}\n"
            f"Customer segment: {customer_segment}\n"
            f"Cart value: ${features.get('total_cart_value', 0):.2f}\n"
            f"Confidence: {confidence:.2f}\n"
            f"Planner reasoning: {reasoning}"
        )

        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=CRITIC_SYSTEM_PROMPT),
                    HumanMessage(content=rewrite_prompt),
                ]
            ),
            timeout=CRITIC_LLM_TIMEOUT_SECONDS,
        )

        output = response.content if hasattr(response, "content") else str(response)

        # Parse JSON from LLM output
        import json

        match = re.search(r"\{.*\}", output, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            fallback_action = parsed.get("action", "NO_ACTION")
            fallback_reasoning = parsed.get("reasoning", "Critic rewrite")

            logger.info(
                f"Critic rewrote '{proposed_action}' → '{fallback_action}' for session {session_id}"
            )
            return {
                "action": fallback_action,
                "reasoning": f"Critic rewrite: {fallback_reasoning}",
                "source": "system_2_critic_rewrite",
                "opa_allowed": False,
            }

    except Exception as e:
        logger.warning(f"Critic LLM rewrite failed: {e}")

    # Step 3: LLM rewrite failed — hard NO_ACTION
    logger.warning(
        f"Critic defaulting to NO_ACTION for session {session_id} (denied: {proposed_action})"
    )
    return {
        "action": "NO_ACTION",
        "reasoning": f"OPA denied '{proposed_action}': policy violation",
        "source": "system_2_critic_rejected",
        "opa_allowed": False,
    }


async def close_critic():
    """Clean up critic LLM resources."""
    global _llm
    _llm = None
    logger.info("Critic agent closed")
