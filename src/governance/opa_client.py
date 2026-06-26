from typing import Optional

import httpx
from loguru import logger

from src.config import settings


class OPAClient:
    """Async client for Open Policy Agent (OPA) /v1/data evaluation."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.opa_url.replace("/v1/data/ecommerce/allow", "")
        self.policy_path = "ecommerce/allow"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def evaluate(self, action: str, customer: dict, features: dict) -> bool:
        """
        Ask OPA if action is allowed.
        Returns True if allowed, False otherwise.
        """
        url = f"{self.base_url}/v1/data/{self.policy_path}"
        payload = {
            "input": {
                "action": action,
                "customer": customer,
                "features": features,
            }
        }

        try:
            client = await self._get_client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            allowed = result.get("result", False)
            logger.debug(f"OPA evaluation for {action}: {allowed}")
            return bool(allowed)
        except Exception as e:
            logger.warning(f"OPA unreachable ({e}). Falling back to Python rules.")
            return self._python_fallback(action, customer, features)

    def _python_fallback(self, action: str, customer: dict, features: dict) -> bool:
        """Mirror of Rego logic for offline/fallback use."""
        if action == "APPLY_DISCOUNT":
            if customer.get("discounts_this_month", 0) >= 3:
                return False
            if customer.get("last_discount_within_hours", 999) < 24:
                return False
            if features.get("total_cart_value", 0) <= 50:
                return False
            return True

        if action == "SHOW_URGENCY":
            return (
                features.get("inventory_level", 100) < 10
                and features.get("intent") == "CHECKOUT_INTENT"
            )

        if action == "SEND_ABANDON_EMAIL":
            return (
                features.get("session_duration_sec", 0) > 300
                and features.get("cart_adds", 0) > 0
                and features.get("checkouts", 0) == 0
            )

        return False

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
