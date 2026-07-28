from __future__ import annotations

import json
from datetime import datetime
import httpx
from loguru import logger

from langfuse.decorators import observe
from src.config import settings

_http_client: httpx.AsyncClient | None = None

HIGH_RISK_ACTIONS = frozenset({"ISSUE_DISCOUNT", "APPLY_DISCOUNT", "REFUND", "CHARGEBACK"})

def _json_serialize_helper(obj):
    """Fallback serializer for objects like datetime."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

async def _get_shared_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


class OPAClient:
    """Async client for Open Policy Agent (OPA) policy evaluation.

    Fail-closed: if OPA is unreachable or times out, high-risk actions are denied.
    """

    def __init__(self, base_url: str | None = None, policy_package: str = "governance"):
        self.base_url = (base_url or settings.opa_url).rstrip("/")
        self.policy_package = policy_package
        self._eval_url = f"{self.base_url}/v1/data/{policy_package}/allow"

    @observe(as_type="generation")
    async def evaluate(
        self,
        action: str,
        intent: str = "",
        discount_value: float = 0.0,
        customer: dict | None = None,
        features: dict | None = None,
    ) -> bool:
        """Ask OPA if action is allowed.

        Returns True if allowed, False otherwise.
        On connection/timeout errors, defaults to False for high-risk actions (fail-closed).
        """
        raw_payload = {
            "input": {
                "action": action,
                "intent": intent,
                "discount_value": discount_value,
                "customer": customer or {},
                "features": features or {},
            }
        }

        try:
            # Convert payload using default handler for datetime
            payload = json.loads(
                json.dumps(raw_payload, default=_json_serialize_helper)
            )

            client = await _get_shared_client()
            response = await client.post(self._eval_url, json=payload)
            response.raise_for_status()
            result = response.json()
            allowed = bool(result.get("result", False))
            logger.debug(f"OPA evaluate({action}): {allowed}")
            return allowed
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            is_high_risk = action in HIGH_RISK_ACTIONS
            logger.error(
                f"OPA unreachable ({type(e).__name__}: {e}). "
                f"action={action} high_risk={is_high_risk} -> fail-closed"
            )
            return False
        except Exception as e:
            logger.error(f"OPA unexpected error: {e}")
            return False

    async def close(self):
        global _http_client
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None