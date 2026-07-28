<h1 align="center">Real-Time Intent Transformer</h1>

<p align="center">
  <img src="assets/ban.png" alt="Real-Time Intent Transformer" width="100%">
</p>

<p align="center">
  <b>A production-grade, dual-path e-commerce intent classification system with deterministic fast-path (System 1), LangGraph agentic reasoning (System 2), OPA governance, background meta-cognition, and end-to-end observability.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/tests-261%2F261%20passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-71%25-yellowgreen" alt="Coverage">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## What Problem Does This Solve?

Traditional personalization engines optimize for conversion at the expense of profit margin. A standard predictive model (like XGBoost) can easily detect when a user is about to abandon a $2,000 cart and reflexively fire a 10% discount. It drives the sale, but it is a blunt instrument—it lacks the semantic context to know if the user was actually price-sensitive, or if they were just confused about a product feature and needed a comparison guide.

The Real-Time Intent Transformer solves this by bridging the gap between fast, probabilistic machine learning and deep, contextual AI reasoning. It is a closed-loop, neuro-symbolic intelligence engine that protects both conversion rates and profit margins.

### The Core Mechanics

Instead of reacting to raw metrics, the engine translates behavior into strategy:

- **The Intent (What We Classify):** We aren't just looking at clicks. The engine classifies complex psychological states in real time: Price Sensitive, Comparing Features, High Conviction, Hesitant, or Churn Risk.
- **The Action (What Runs):** Based on that classified intent, the engine dispatches a targeted intervention from a predefined action space. If the intent is Price Sensitive, the action is `APPLY_DISCOUNT`. If the intent is Comparing Features, the action is `SHOW_COMPARISON_TOOL`.
- **The Engine (The Decision Matrix):** Interventions are never fired blindly. Every execution runs based on the mathematical fusion of live streaming features (page views, cart adds), historical memory (past purchases, discount abuse), and strict Open Policy Agent (OPA) governance rules that dictate exactly what is legally and financially permissible.

> **"Perceive → Reason → Govern → Execute → Learn"**

Every clickstream event flows through a mathematically governed, dual-path architecture:

- **System 1 (Fast Perception):** Built for high-throughput stream ingestion. An optimized ML ensemble handles 80% of standard traffic, dispensing deterministic actions (urgency, standard cart recovery) in <50ms on CPU, with zero external API dependencies.
- **System 2 (Deep Reasoning):** When a session is complex, novel, or ambiguous, the pipeline escalates to an LLM-powered agentic orchestrator. Using Planners, Critics, and GraphRAG retrieval, it reasons through the context of user behavior to protect margins (e.g., dynamically fetching a firmware update article to resolve a user's hesitation, rather than needlessly burning a $200 discount).
- **Enterprise Governance:** Agents are inherently unpredictable, which is a non-starter for production finance and marketing. Every proposed AI action is forced through an Open Policy Agent (OPA) fail-closed sandbox. The system is physically incapable of executing an intervention that violates predefined business logic or margin constraints.
- **Action-Aware Learning:** A background meta-cognitive evaluator continuously tracks the cryptographic audit ledger, monitoring the true economic ROI of the engine's decisions and automatically detecting mathematical drift over time.

---

## Architecture

### Dual-Path Design

```
                      ┌─────────────────────────────┐
                      │     Incoming Click Event     │
                      └──────────────┬──────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │   Complexity Router          │
                      │   (confidence < threshold    │
                      │    or complex intent?)       │
                      └──────┬───────────────┬──────┘
                             │               │
                ┌────────────▼──┐    ┌───────▼────────────┐
                │  System 1     │    │  System 2           │
                │  Fast Path    │    │  Agentic Path       │
                │  (<50ms)      │    │  (unlimited)        │
                │               │    │                     │
                │  ML Ensemble  │    │  LLM Planner        │
                │  + Rules      │    │  + GraphRAG         │
                │  + Markov     │    │  + Critic Agent     │
                └───────┬───────┘    └────────┬────────────┘
                        │                     │
                        │            ┌────────▼────────────┐
                        │            │  OPA Critic         │
                        │            │  (governance gate)  │
                        │            └────────┬────────────┘
                        │                     │
                ┌───────▼─────────────────────▼──────┐
                │       Action Dispatcher             │
                │  (suppression + audit ledger)       │
                └────────────────┬────────────────────┘
                                 │
                ┌────────────────▼────────────────────┐
                │   Background Meta-Cognitive Evaluator│
                │   (drift detection + LLM-as-Judge)  │
                └─────────────────────────────────────┘
```

### System 1 — Deterministic Fast Path (<50ms)

| Stage | Component | Technology | Latency |
|-------|-----------|------------|---------|
| **Ingestion** | REST / Kafka | FastAPI, aiokafka | Async streaming |
| **Hydration** | Session + Event Store | SQLite / Redis / PostgreSQL | <5ms |
| **Perception** | Feature Engineer | **Polars** | <5ms (18 behavioral features) |
| **Reasoning** | ML Ensemble | Rule heuristic + Markov chain + sklearn RF + XGBoost | <10ms rule, <50ms ML |
| **Governance** | OPA Policy Engine | OPA/Rego v1 + Python fallback | 50ms timeout, fail-closed |
| **Execution** | Action Dispatcher | FastAPI | 6 action types with suppression |
| **Ledger** | Audit Trail | PostgreSQL / SQLite | Immutable, ON CONFLICT DO UPDATE for status |

### System 2 — Agentic Reasoning (LangGraph)

When confidence is below threshold or intent is complex (`CHURN_RISK`, `LOYAL_RETURNER`), sessions escalate to the agentic path:

1. **LLM Planner** — Proposes an action using session context + GraphRAG product retrieval
2. **GraphRAG Tools** — Neo4j graph queries for product relationships and customer history
3. **Critic Agent** — Validates the proposed action against OPA governance policies
   - If OPA allows → approve unchanged
   - If OPA denies → rewrite to compliant fallback via LLM
   - If rewrite fails → hard `NO_ACTION`

State persistence uses LangGraph checkpointing (`PostgresSaver` in production, `MemorySaver` for local dev).

### Background Meta-Cognition

A persistent background worker periodically:

- Fetches recent actions from the PostgreSQL ledger
- Correlates actions with user conversion events
- Uses LLM-as-a-Judge to diagnose failed interventions
- Detects model drift (declining efficacy over time)
- Persists aggregated metrics to `evaluation_metrics` table

---

## Production Readiness Checklist

| Priority | Item | Status |
|----------|------|--------|
| **P0** | `eval()` RCE patched → `json.loads()` | ✅ Fixed |
| **P0** | OPA policy deny rules enforced (Rego v1) | ✅ Fixed |
| **P0** | OPA client package name aligned | ✅ Fixed |
| **P0** | Deterministic action idempotency keys | ✅ Fixed |
| **P0** | ActionDispatcher singleton (suppression works) | ✅ Fixed |
| **P1** | LangGraph PostgreSQL checkpointing | ✅ Fixed |
| **P1** | OPA timeout & async fallback (50ms) | ✅ Fixed |
| **P1** | Defensive timeouts (critic 15s, evaluator 30s, Neo4j 5s) | ✅ Fixed |
| **P1** | LLM concurrency limiter (Semaphore) | ✅ Fixed |
| **P1** | SQLite async I/O (`asyncio.to_thread`) | ✅ Fixed |
| **P1** | Orchestrator wired into REST API | ✅ Fixed |
| **P2** | State bounding (`MAX_STATE_EVENTS=50`) | ✅ Fixed |
| **P2** | Event store TTL cleanup (24h) | ✅ Fixed |
| **P2** | Platt scaling sigmoid calibration | ✅ Fixed |
| **P2** | Deterministic rule classifier tie-breaking | ✅ Fixed |
| **P2** | Per-instance OPA HTTP client | ✅ Fixed |
| **P2** | Prometheus metrics instrumented | ✅ Fixed |
| **P3** | CORS configurable origins | ✅ Fixed |
| **P3** | Secrets removed from config defaults | ✅ Fixed |

**Test Suite: 261/261 passing | Coverage: 71%**

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Kafka + OPA)
- (Optional) Ollama for local LLM inference
- (Optional) PostgreSQL for checkpointing and audit ledger
- (Optional) Neo4j for GraphRAG product retrieval

### Installation

```bash
# 1. Clone repository
git clone https://github.com/aragit/real-time-intent-transformer.git
cd real-time-intent-transformer

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Start infrastructure (Kafka + OPA)
docker compose -f docker/docker-compose.yml up -d

# 5. Configure environment
cp .env.example .env  # edit with your settings

# 6. Launch API
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### With Pre-Trained Model

```bash
python scripts/generate_clickstream.py
python scripts/train_model.py
# Saves models/intent_classifier.joblib
```

### API Reference

Interactive docs: `http://localhost:8000/docs`

### Event Ingestion

```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_001",
    "customer_id": "cust_001",
    "action": "add_to_cart",
    "product_id": "prod_001",
    "category": "electronics",
    "value": 99.99
  }'
```

### Intent Prediction (Dual-Path Orchestrator)

```bash
curl http://localhost:8000/sessions/sess_001/intent
```

**Response:**

```json
{
  "session_id": "sess_001",
  "intent": "CHECKOUT_INTENT",
  "confidence": 0.857,
  "method": "rule_based",
  "features": {
    "session_duration_sec": 245.0,
    "page_views": 3,
    "cart_adds": 2,
    "checkouts": 1,
    "total_cart_value": 199.98
  },
  "predicted_next_state": "PURCHASE"
}
```

### Session Features

```bash
curl http://localhost:8000/sessions/sess_001/features
```

### Markov Chain Prediction

```bash
curl http://localhost:8000/sessions/sess_001/markov
```

### Intent Distribution

```bash
curl http://localhost:8000/intents/distribution
```

### Health Check

```bash
curl http://localhost:8000/health
```

---

## Testing

### Full Test Suite

```bash
# Run all tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing

# Run specific test categories
pytest tests/test_critic_security.py -v      # Prompt injection security tests
pytest tests/test_evaluator.py -v            # Evaluator agent tests
pytest tests/test_orchestrator.py -v         # Orchestrator graph tests
pytest tests/test_governance.py -v           # OPA + business rules tests
pytest tests/test_latency_benchmark.py -v    # Performance regression tests
pytest tests/test_integration.py -v          # End-to-end flows
```

### Test Suite Breakdown (261 Tests)

| Category | Count | Coverage |
|----------|-------|----------|
| Evaluator Agent | 29 | Core batch processing, drift detection, LLM analysis |
| Evaluator Worker | 8 | Lifecycle, Prometheus metrics, error handling |
| Critic Agent | 12 | OPA validation, rewrite, hard rejection |
| Critic Security | 8 | Prompt injection, markdown jailbreak, Unicode bypass |
| Orchestrator Graph | 15 | System 1/2 routing, state transitions, checkpointing |
| Pipeline | 18 | Hydration, feature engineering, governance |
| API Routes | 22 | All endpoints, error handling |
| Models | 15 | Events, actions, features, intents |
| Memory Stores | 18 | SQLite, Redis, session/event stores |
| Reasoning | 12 | ML ensemble, Markov chain, rule classifier |
| Execution | 15 | Dispatcher, suppressor, ledger |
| Governance | 12 | OPA client, business rules |
| Integration | 12 | End-to-end flows |
| Benchmarks | 18 | Latency regression tests |
| Feature Engineering | 11 | Polars performance, edge cases |
| Kafka Ingestion | 16 | Producer, consumer, lifecycle, malformed handling |
| SLM Enrichment | 20 | Search query enrichment, intent signals, caching |

---

## Observability

### Langfuse — Distributed Tracing

Langfuse provides end-to-end visibility into the dual-path pipeline:

```
       ┌─────────────────────────────────────────────────────────┐
       │                   FastAPI / API Route                   │
       └────────────────────────────┬────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
┌─────────────────────────┐                     ┌─────────────────────────┐
│       System 1          │                     │        System 2         │
│  Fast-Path / OPA Policy │                     │  LangGraph Multi-Agent  │
└───────────┬─────────────┘                     └───────────┬─────────────┘
            │                                               │
            ▼                                               ▼
   [@observe Decorator]                          [Langfuse CallbackHandler]
   - Latency tracking (<15ms)                    - Node-by-node state spans
   - Fallback evaluations                        - Graph state inputs/outputs
            │                                               │
            └───────────────────────┬───────────────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │      Langfuse Cloud       │
                      │  Tracing & Analytics UI   │
                      └───────────────────────────┘
```

**Setup:**

```bash
# Option A: Langfuse Cloud (recommended for quick start)
# Sign up at https://cloud.langfuse.com → Create project → Copy keys

echo "LANGFUSE_PUBLIC_KEY=pk-lf-..." >> .env
echo "LANGFUSE_SECRET_KEY=sk-lf-..." >> .env
echo "LANGFUSE_HOST=https://cloud.langfuse.com" >> .env

# Option B: Self-hosted
# docker compose -f docker/docker-compose.langfuse.yml up -d
```

**Traces Captured:**

| Component | Tracing | What's Captured |
|-----------|---------|-----------------|
| **OPA Client** | `@observe()` | Evaluation latency, fallback path, allow/deny decisions |
| **Classify Endpoint** | `@observe()` | Full request lifecycle for intent prediction |
| **LangGraph Orchestrator** | `CallbackHandler` | Planner, GraphRAG tools, Critic agent as nested spans |
| **Evaluator Agent** | `@observe()` | Background batch traces, LLM analysis spans |

> **Note:** The test suite automatically disables external telemetry via `LANGFUSE_SDK_DISABLED=true` in `tests/conftest.py` to prevent suite latency or external network dependency failures.

### Prometheus — Operational Metrics

Prometheus metrics are exposed for scraping:

```yaml
# Add to your prometheus.yml:
scrape_configs:
  - job_name: "intent-transformer"
    static_configs:
      - targets: ["localhost:8000"]
```

**Available Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method/endpoint/status |
| `http_request_duration_seconds` | Histogram | HTTP request latency |
| `events_ingested_total` | Counter | Total click events ingested |
| `intent_predictions_total` | Counter | Intent predictions by class |
| `actions_dispatched_total` | Counter | Actions dispatched by type |
| `actions_suppressed_total` | Counter | Actions suppressed by cooldown |
| `evaluator_drift_flagged` | Gauge | Model drift indicator (1=drifted) |
| `evaluator_batch_conversion_rate` | Gauge | Latest batch conversion rate |
| `evaluator_actions_evaluated_total` | Counter | Total actions evaluated |

---

## Governance & Safety

- **OPA/Rego v1 policies** with Python fallback for offline evaluation
- **Anti-gaming:** No duplicate discounts within 15 minutes; max 3 discounts/month
- **Fairness guardrails:** No demographic-based pricing discrimination
- **Action suppression:** Deduplication within configurable time windows
- **Audit trail:** Immutable ledger of every dispatched action with intent, confidence, and reason
- **Deterministic idempotency:** SHA-256 keys from `session_id:action:minute_bucket` prevent duplicate actions
- **Fail-closed:** OPA unreachable → deny high-risk actions (`APPLY_DISCOUNT`, `REFUND`, `CHARGEBACK`)

---

## Technology Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| **Runtime** | Python 3.11+ | Core language |
| **API** | FastAPI + Uvicorn | Async HTTP server |
| **Agentic** | LangGraph ≥0.2.0 | Stateful multi-agent orchestration |
| **LLM** | Ollama / OpenAI | Local or cloud LLM inference |
| **GraphRAG** | Neo4j | Product relationship queries |
| **Policy** | OPA/Rego v1 | Governance & compliance rules |
| **ML** | scikit-learn + XGBoost | Ensemble classification with Platt scaling |
| **Features** | Polars | High-performance data processing |
| **Streaming** | Apache Kafka (KRaft) | Clickstream event ingestion |
| **Storage** | PostgreSQL + SQLite | Ledger, checkpointing, sessions |
| **Cache** | Redis | Session state caching |
| **Observability** | Langfuse | Distributed tracing & LLM monitoring |
| **Metrics** | Prometheus | Operational metrics |
| **Testing** | pytest + pytest-asyncio | 261 tests, 71% coverage |

---

## Project Structure

```
real-time-intent-transformer/
├── src/
│   ├── agents/
│   │   ├── orchestrator.py      # LangGraph dual-path router
│   │   ├── planner.py           # LLM Planner Agent
│   │   ├── critic.py            # Critic Agent (OPA validation)
│   │   ├── evaluator.py         # Background Meta-Cognitive Evaluator
│   │   └── tools/
│   │       └── graph_retriever.py  # Neo4j GraphRAG tools
│   ├── api/routes/
│   │   ├── events.py            # Event ingestion endpoints
│   │   ├── sessions.py          # Intent prediction (orchestrator)
│   │   ├── intents.py           # Intent distribution
│   │   ├── actions.py           # Action history
│   │   ├── customers.py         # Customer profiles
│   │   └── health.py            # Health checks
│   ├── governance/
│   │   ├── opa_client.py        # OPA/Rego policy engine (per-instance client)
│   │   └── business_rules.py    # Python fallback rules
│   ├── execution/
│   │   ├── dispatcher.py        # Action dispatcher
│   │   ├── suppressor.py        # Deduplication/suppression
│   │   ├── pg_ledger.py         # PostgreSQL ledger (immutable + status updates)
│   │   └── sqlite_ledger.py     # SQLite ledger
│   ├── memory/
│   │   ├── session_store.py     # Session state store (async SQLite)
│   │   ├── event_store.py       # Event history store (async SQLite)
│   │   ├── sqlite_store.py      # SQLite async backend
│   │   └── redis_store.py       # Redis backend
│   ├── reasoning/
│   │   ├── ml_ensemble.py       # ML ensemble with Platt scaling
│   │   ├── markov_model.py      # Markov chain predictor
│   │   ├── rule_classifier.py   # Rule-based classifier (deterministic ties)
│   │   └── slm_enrichment.py    # SLM enrichment
│   ├── perception/
│   │   └── feature_engineer.py  # Polars feature engineering
│   ├── observability/
│   │   ├── metrics.py           # Prometheus metrics (instrumented)
│   │   └── logging.py           # Loguru configuration
│   ├── ingestion/
│   │   ├── kafka_consumer.py    # Kafka consumer (async)
│   │   └── kafka_producer.py    # Kafka producer
│   ├── workers/
│   │   └── evaluator_worker.py  # Background evaluator loop
│   ├── models/                  # Pydantic data models
│   ├── config.py                # Settings (pydantic-settings)
│   ├── main.py                  # FastAPI app (CORS + metrics middleware)
│   └── pipeline.py              # System 1 hot-path pipeline
├── policies/
│   └── ecommerce.rego           # OPA Rego v1 policies (deny guards)
├── tests/                       # 261 tests, 100% pass rate
├── docker/
│   └── docker-compose.yml       # Kafka (KRaft) + OPA
├── scripts/
│   ├── generate_clickstream.py  # Synthetic data generation
│   └── train_model.py           # Model training
├── pyproject.toml               # Project config + pinned dependencies
└── README.md
```

---

## Configuration

Create `.env` from `.env.example`:

```bash
# Required
DATABASE_URL=sqlite:///./intent_transformer.db
OPA_URL=http://localhost:8181

# LLM (Ollama local)
LLM_PROVIDER=ollama
LLM_MODEL=qwen3-coder:4b
LLM_BASE_URL=http://localhost:11434/v1

# Optional: PostgreSQL for ledger + checkpointing
USE_PG_LEDGER=false
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/intent_transformer

# Optional: Langfuse observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional: Redis for session caching
USE_REDIS_STORE=false
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=["http://localhost:3000"]

# Routing threshold
SYSTEM_2_CONFIDENCE_THRESHOLD=0.70
```

---

## Recent Hardening & Audit

This repository underwent a comprehensive security and architectural audit. Key fixes applied:

- **Security:** Removed `eval()` RCE vulnerability; replaced with `json.loads()`
- **Governance:** Fixed OPA Rego v1 deny rules to actually block violations; aligned package names
- **Architecture:** Wired LangGraph orchestrator into REST API; System 2 is now reachable
- **Performance:** SQLite I/O offloaded to thread pool; async event loop no longer blocked
- **Statistics:** Added Platt scaling sigmoid calibration; removed +1 smoothing bias
- **Correctness:** Deterministic tie-breaking in rule classifier; per-instance HTTP clients
- **Observability:** Instrumented Prometheus metrics; configurable CORS
- **Testing:** 261 tests passing, 0 failures

---

## Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| System 1 latency (p95) | <50ms | ~15-30ms |
| System 2 latency (p95) | <5s | ~1-3s (local LLM) |
| OPA evaluation | <15ms | ~5-10ms |
| Feature engineering | <5ms | ~2-3ms |
| Throughput | 1K events/sec | TBD |

```bash
# Run benchmarks
pytest tests/test_latency_benchmark.py -v
```

---

## Citation

If you use this software in your research or product, please cite it. Click the **"Cite this repository"** button on the GitHub sidebar, or use:

```bibtex
@software{real_time_intent_transformer_2026,
  author    = {{Real-Time Intent Transformer Contributors}},
  title     = {{Real-Time Intent Transformer: A Dual-Path Neuro-Symbolic Pipeline for E-Commerce Intent Classification}},
  year      = {2026},
  url       = {https://github.com/aragit/real-time-intent-transformer},
  license   = {MIT}
}
```

> **Citation format:** [CITATION.cff](CITATION.cff) (GitHub renders a "Cite this repository" button automatically from this file)

---

## Contributing

Contributions welcome in:

- Additional intent classes (BARGAIN_HUNTER, GIFT_SHOPPER)
- Real-time bidding (RTB) integration patterns
- Multi-modal intent (image search, voice queries)
- Reinforcement learning for action optimization
- Redis-backed suppressor for horizontal scaling
- Load testing and performance benchmarks

---

## License

MIT License — AI Engineering Portfolio

---

<p align="center">
  <sub>Built with FastAPI, LangGraph, Polars, Kafka, and a deep respect for deterministic reasoning.</sub>
</p>
