from __future__ import annotations

import json
from datetime import datetime

import httpx
from langfuse.decorators import observe
from loguru import logger

from src.config import settings

HIGH_RISK_ACTIONS = frozenset({"ISSUE_DISCOUNT", "APPLY_DISCOUNT", "REFUND", "CHARGEBACK"})


def _json_serialize_helper(obj):
    """Fallback serializer for objects like datetime."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class OPAClient:
    """Async client for Open Policy Agent (OPA) policy evaluation.

    Fail-closed: if OPA is unreachable or times out, high-risk actions are denied.
    Each instance owns its own httpx.AsyncClient to avoid cross-instance corruption.
    """

    def __init__(self, base_url: str | None = None, policy_package: str = "governance"):
        self.base_url = (base_url or settings.opa_url).rstrip("/")
        self.policy_package = policy_package
        self._eval_url = f"{self.base_url}/v1/data/{policy_package}/allow"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=2.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

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
            payload = json.loads(
                json.dumps(raw_payload, default=_json_serialize_helper)
            )

            client = await self._get_client()
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
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
