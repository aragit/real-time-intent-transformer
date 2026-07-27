# Task Report: Governance Overhaul

**Commit:** `aa3d6d2`  
**Date:** 2026-07-28  
**Scope:** OPA client refactor, Rego policy modernization, fail-closed error handling, infrastructure cleanup

---

## What Was Done

### 1. OPAClient Refactored (`src/governance/opa_client.py`)

**Before:** The `evaluate()` method took positional args `(action, customer, features)`, carried a Python fallback that duplicated all Rego logic, and had a 50ms timeout that silently fell back to the Python rules engine on any error.

**After:**
- `evaluate()` now accepts explicit keyword arguments: `action`, `intent`, `discount_value`, `customer`, `features`. This allows OPA policies to reason about intent and discount tiers directly.
- Python fallback removed entirely. OPA is the single source of truth for governance decisions.
- Fail-closed on all errors: `ConnectError`, `TimeoutException`, and `HTTPStatusError` all return `False`. High-risk actions (`APPLY_DISCOUNT`, `REFUND`, `CHARGEBACK`, `ISSUE_DISCOUNT`) are explicitly denied on OPA unreachability.
- Timeout increased from 50ms to 5s (connect: 2s) since the Python fallback is gone.
- Shared `httpx.AsyncClient` is checked for `is_closed` before reuse, preventing stale connection errors.
- `HIGH_RISK_ACTIONS` constant added for clear classification of dangerous actions.

### 2. New Governance Policy (`policies/governance.rego`)

Created a dedicated governance policy package (`governance.allow`) with three tiers of rules:

| Rule | Action | Condition | Effect |
|------|--------|-----------|--------|
| **Hard Limit** | `ISSUE_DISCOUNT` | `discount_value <= 20` | Allow |
| **Intent Guard** | `ISSUE_DISCOUNT` | `intent == "CHECKOUT_INTENT"` | Allow |
| **Intent Guard** | `ISSUE_DISCOUNT` | `intent == "BROWSING"` | Deny |
| **Safe Actions** | `LOG_ANALYTICS`, `RECOMMEND_PRODUCT` | Always | Allow |
| **Default** | Any unrecognized action | N/A | Deny |

### 3. Rego v1 Syntax Migration (`policies/ecommerce.rego`)

All rules updated from deprecated Rego v0 syntax to v1:
- `allow { ... }` → `allow if { ... }`
- `deny { ... }` → `deny if { ... }`

### 4. Pipeline & Critic Updated

- **`src/pipeline.py`**: `_run_governance()` now passes `intent` through to OPA. Dead `BusinessRules` import and `_get_rules()` singleton removed.
- **`src/agents/critic.py`**: `run_critic()` now passes `intent` and `discount_value` from features to OPA's `evaluate()`.
- **`src/config.py`**: `opa_url` simplified from full path (`http://localhost:8181/v1/data/ecommerce/allow`) to base URL (`http://localhost:8181`). The OPAClient constructs the full path internally.

### 5. Docker Infrastructure Simplified (`docker/docker-compose.yml`)

- **Kafka**: Migrated from Confluent Zookeeper-based setup to Apache Kafka KRaft mode (no Zookeeper dependency). Single container, simpler config.
- **OPA**: Changed from loading only `ecommerce.rego` to loading the entire `/policies/` directory, so both `ecommerce.rego` and `governance.rego` are active simultaneously.

### 6. Tests Updated

- **`tests/test_governance.py`**: Rewritten from BusinessRules-only tests to comprehensive OPA client tests covering all governance scenarios, fail-closed behavior, payload structure validation, and shared client lifecycle.
- **`tests/test_critic.py`**: Updated assertion for `mock_opa.evaluate.assert_called_once_with()` to match the new keyword-argument signature.
- **Result:** 263 tests passing (was 262), zero new regressions.

---

## What Changed Architecturally

```
BEFORE:                              AFTER:
                                    
Event → OPAClient.evaluate()        Event → OPAClient.evaluate()
  → OPA HTTP (50ms timeout)           → OPA HTTP (5s timeout)
  → On error: Python fallback         → On error: Fail-closed (deny)
  → Rego v0 syntax                    → Rego v1 syntax
  → Single ecommerce.rego            → ecommerce.rego + governance.rego
  → Zookeeper + Kafka               → KRaft Kafka (no Zookeeper)
```

The system went from a "dual governance" model (OPA primary, Python fallback) to a single-source-of-truth model where OPA is authoritative and failures are explicitly denied rather than silently bypassed.

---

## Test Results

```
263 passed, 5 failed, 10 errors in 96.62s
```

- **263 passed** — All governance, critic, pipeline, API, and reasoning tests pass.
- **5 failed** — Pre-existing: 3 PostgreSQL ledger concurrency tests (need live DB), 2 latency benchmark tests (environment-dependent).
- **10 errors** — Pre-existing: PostgreSQL ledger tests (connection refused, no test DB).

No new failures introduced by this task.

---

## Files Modified (9 files, +419/-167 lines)

| File | Change |
|------|--------|
| `policies/governance.rego` | **New** — OPA governance policy |
| `policies/ecommerce.rego` | Rego v1 syntax migration |
| `src/governance/opa_client.py` | Full refactor: new API, fail-closed, no fallback |
| `src/agents/critic.py` | Updated evaluate() call signature |
| `src/pipeline.py` | Pass intent to OPA, remove dead BusinessRules code |
| `src/config.py` | Simplify opa_url to base URL |
| `docker/docker-compose.yml` | KRaft Kafka, OPA loads full policies dir |
| `tests/test_governance.py` | Rewritten for OPA client testing |
| `tests/test_critic.py` | Updated mock assertion |
