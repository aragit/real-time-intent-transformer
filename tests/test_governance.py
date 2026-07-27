from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.governance.opa_client import OPAClient, _http_client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


class TestOPAClientGovernance:
    """Unit tests for OPAClient against the governance policy."""

    @pytest.fixture(autouse=True)
    def _reset_client(self):
        """Reset the global httpx client before each test."""
        import src.governance.opa_client as mod
        mod._http_client = None
        yield
        mod._http_client = None

    @pytest.mark.asyncio
    async def test_15_percent_discount_checkout_allowed(self):
        """Rule: 15% discount for CHECKOUT_INTENT user is ALLOWED."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": True})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(
                action="ISSUE_DISCOUNT",
                intent="CHECKOUT_INTENT",
                discount_value=15.0,
            )

        assert result is True
        mock_http.post.assert_called_once()
        payload = mock_http.post.call_args[1]["json"]["input"]
        assert payload["action"] == "ISSUE_DISCOUNT"
        assert payload["discount_value"] == 15.0
        assert payload["intent"] == "CHECKOUT_INTENT"

    @pytest.mark.asyncio
    async def test_25_percent_discount_denied(self):
        """Rule 1 (Hard Limit): 25% discount is DENIED regardless of intent."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": False})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(
                action="ISSUE_DISCOUNT",
                intent="CHECKOUT_INTENT",
                discount_value=25.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_10_percent_browsing_denied(self):
        """Rule 2 (Intent Guard): 10% discount for BROWSING user is DENIED."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": False})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(
                action="ISSUE_DISCOUNT",
                intent="BROWSING",
                discount_value=10.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_log_analytics_allowed(self):
        """Rule 3 (Safe Actions): LOG_ANALYTICS is ALLOWED."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": True})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(action="LOG_ANALYTICS")

        assert result is True

    @pytest.mark.asyncio
    async def test_recommend_product_allowed(self):
        """Rule 3 (Safe Actions): RECOMMEND_PRODUCT is ALLOWED."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": True})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(action="RECOMMEND_PRODUCT")

        assert result is True

    @pytest.mark.asyncio
    async def test_fail_closed_on_connect_error(self):
        """Fail-safe: ConnectError -> deny high-risk actions."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")

        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(
                action="ISSUE_DISCOUNT",
                intent="CHECKOUT_INTENT",
                discount_value=15.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_fail_closed_on_timeout(self):
        """Fail-safe: TimeoutException -> deny all actions."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")

        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.TimeoutException("Request timed out")

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(action="LOG_ANALYTICS")

        assert result is False

    @pytest.mark.asyncio
    async def test_fail_closed_on_http_error(self):
        """Fail-safe: HTTP 500 -> deny all actions."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")

        mock_resp = _mock_response({"error": "internal error"}, status_code=500)
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(action="ISSUE_DISCOUNT", discount_value=5.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_fail_closed_on_unknown_action(self):
        """Unknown actions are denied by default deny."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": False})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            result = await client.evaluate(action="RANDOM_ACTION_XYZ")

        assert result is False

    @pytest.mark.asyncio
    async def test_client_close_cleans_up(self):
        """close() should clean up the shared httpx client."""
        import src.governance.opa_client as mod
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        mod._http_client = mock_http

        client = OPAClient(base_url="http://mock:8181")
        await client.close()

        mock_http.aclose.assert_called_once()
        assert mod._http_client is None

    @pytest.mark.asyncio
    async def test_shared_client_reuse(self):
        """Verify that multiple evaluate() calls reuse the same httpx client."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": True})
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            await client.evaluate(action="LOG_ANALYTICS")
            await client.evaluate(action="RECOMMEND_PRODUCT")

        assert mock_http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_payload_structure(self):
        """Verify the exact payload structure sent to OPA."""
        client = OPAClient(base_url="http://mock:8181", policy_package="governance")
        mock_resp = _mock_response({"result": True})
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp

        with patch("src.governance.opa_client._get_shared_client", return_value=mock_http):
            await client.evaluate(
                action="ISSUE_DISCOUNT",
                intent="CHECKOUT_INTENT",
                discount_value=15.0,
                customer={"id": "cust_123"},
                features={"session_duration_sec": 300},
            )

        call_args = mock_http.post.call_args
        payload = call_args[1]["json"]
        assert "input" in payload
        assert payload["input"]["action"] == "ISSUE_DISCOUNT"
        assert payload["input"]["intent"] == "CHECKOUT_INTENT"
        assert payload["input"]["discount_value"] == 15.0
        assert payload["input"]["customer"] == {"id": "cust_123"}
        assert payload["input"]["features"] == {"session_duration_sec": 300}


class TestBusinessRules:
    """Tests for the Python fallback governance rules."""

    def test_discount_allowed(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "APPLY_DISCOUNT", {"discounts_this_month": 1}, {"total_cart_value": 100}
        )
        assert allowed is True
        assert reason == ""

    def test_discount_cap_reached(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "APPLY_DISCOUNT", {"discounts_this_month": 3}, {"total_cart_value": 100}
        )
        assert allowed is False
        assert reason == "MAX_DISCOUNT_CAP_REACHED"

    def test_anti_gaming_cooldown(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "APPLY_DISCOUNT", {"last_discount_within_hours": 12}, {"total_cart_value": 100}
        )
        assert allowed is False
        assert reason == "ANTI_GAMING_COOLDOWN"

    def test_min_cart_value_not_met(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate("APPLY_DISCOUNT", {}, {"total_cart_value": 30})
        assert allowed is False
        assert reason == "MIN_CART_VALUE_NOT_MET"

    def test_urgency_allowed(self):
        from src.governance.business_rules import BusinessRules

        allowed, _ = BusinessRules().evaluate(
            "SHOW_URGENCY", {}, {"inventory_level": 5, "intent": "CHECKOUT_INTENT"}
        )
        assert allowed is True

    def test_urgency_inventory_sufficient(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "SHOW_URGENCY", {}, {"inventory_level": 20, "intent": "CHECKOUT_INTENT"}
        )
        assert allowed is False
        assert reason == "INVENTORY_SUFFICIENT"

    def test_abandon_email_allowed(self):
        from src.governance.business_rules import BusinessRules

        allowed, _ = BusinessRules().evaluate(
            "SEND_ABANDON_EMAIL", {}, {"session_duration_sec": 400, "cart_adds": 2, "checkouts": 0}
        )
        assert allowed is True

    def test_abandon_session_too_short(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "SEND_ABANDON_EMAIL", {}, {"session_duration_sec": 100, "cart_adds": 2, "checkouts": 0}
        )
        assert allowed is False
        assert reason == "SESSION_TOO_SHORT"

    def test_already_purchased_blocks_discount(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "APPLY_DISCOUNT",
            {},
            {"total_cart_value": 100, "action_sequence": ["purchase_complete"]},
        )
        assert allowed is False
        assert reason == "ALREADY_PURCHASED"

    def test_demographic_fairness(self):
        from src.governance.business_rules import BusinessRules

        allowed, reason = BusinessRules().evaluate(
            "APPLY_DISCOUNT",
            {"demographic_segment": "A"},
            {"total_cart_value": 100, "demographic_segment": "B"},
        )
        assert allowed is False
        assert reason == "DEMOGRAPHIC_MISMATCH"
