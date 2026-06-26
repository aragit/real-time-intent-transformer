<h1 align="center">Real-Time Intent Transformer</h1>
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Polars-CD792C" alt="Polars">
  <img src="https://img.shields.io/badge/Kafka-231F20" alt="Kafka">
  <img src="https://img.shields.io/badge/OPA-7D9199" alt="OPA">
  <img src="https://img.shields.io/badge/scikit--learn-F7931E" alt="scikit-learn">
  <img src="https://img.shields.io/badge/XGBoost-EB4226" alt="XGBoost">
  <img src="https://img.shields.io/badge/Pydantic-E92063" alt="Pydantic">
  <img src="https://img.shields.io/badge/pytest-0A9EDC" alt="pytest">
  <img src="https://img.shields.io/badge/Docker-2496ED" alt="Docker">
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

<p align="center">
  <b>A real-time e-commerce intent classification system that ingests clickstream events, engineers behavioral features with Polars, classifies shopping intent via rule-based heuristics and Markov chain state transitions, and triggers adaptive actions with governance guardrails.</b>
</p>

# Real-Time Intent Transformer

A real-time e-commerce intent classification system that ingests clickstream events, engineers behavioral features with Polars, classifies shopping intent via rule-based heuristics and Markov chain state transitions, and triggers adaptive actions with governance guardrails.

* * *

## 🎯 What Problem Does This Solve?

E-commerce platforms lose revenue because they treat all users the same. A user browsing 20 pages without adding to cart needs a different intervention than one with a full cart who started checkout.

**Real-Time Intent Transformer** classifies live shopping sessions into 7 intent categories (BROWSE, COMPARE, CART_BUILDER, CHECKOUT_INTENT, PRICE_SENSITIVE, CHURN_RISK, LOYAL_RETURNER) and dispenses targeted actions (discounts, urgency, abandon recovery) within 50ms — all on CPU, with zero external API dependencies.

> **"Perceive-Reason-Govern-Execute"**: Every clickstream event flows through a 7-layer neuro-symbolic pipeline. The system perceives behavioral patterns, reasons about intent, governs actions against business rules, and executes with suppression and audit.

* * *

## 🏗️ Technical Specification

### Architecture Paradigm

7-layer pipeline aligned with AXIOMIS neuro-symbolic stack:

| Layer | Component | Technology | Role |
|-------|-----------|------------|------|
| **Ingestion** | Kafka Producer/Consumer | `aiokafka`, FastAPI | Clickstream event ingestion and streaming |
| **Perception** | Feature Engineer | **Polars** (not Pandas) | Session windowing, 15+ behavioral features |
| **Reasoning** | Intent Classifier | Rule-based + Markov chain + sklearn RF | <10ms rule heuristic, <50ms ML fallback |
| **Governance** | Policy Engine | OPA/Rego + Python fallback | Discount caps, anti-gaming, fairness guardrails |
| **Execution** | Action Dispatcher | FastAPI | 6 action types with suppression and ledger |
| **Memory** | Session + Customer Store | SQLite | TTL sessions, aggregate profiles, immutable ledger |
| **Meta-Cognition** | Drift Detection | Stub (Phase 2) | Model distribution shift monitoring |

### The Intent Classification Loop


**Key invariant**: No action reaches the user without passing governance. Unvalidated actions are suppressed with a logged reason.

* * *

## 🚀 Applications

### E-Commerce Personalization

- **Dynamic Pricing**: Price-sensitive users receive targeted discounts; loyal returners get rewards
- **Cart Abandonment Recovery**: CHURN_RISK sessions trigger email/SMS before exit
- **Urgency Injection**: CHECKOUT_INTENT users see low-inventory warnings
- **Browse Assistance**: BROWSE/COMPARE users get recommendations and comparison tools

### Behavioral Analytics

- **Real-time Intent Distribution**: Live histogram of session intents across the platform
- **Session Quality Scoring**: Predicted next state via Markov chain (LANDING → BROWSING → CARTING → CHECKOUT)
- **Customer Lifetime Value Segmentation**: Aggregate intent history builds preference vectors

### A/B Testing Infrastructure (Phase 2)

- **Action Variant Assignment**: Documented stub for traffic splitting
- **Outcome Tracking**: Click-through, conversion, revenue attribution (stub)

* * *

## 📦 Installation

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Kafka + OPA + Zookeeper)
- (Optional) Ollama for SLM enrichment (Phase 2)

### Quick Start (Zero GPU, Zero API Key)

```bash
# 1. Clone repository
git clone https://github.com/aragit/real-time-intent-transformer.git
cd real-time-intent-transformer

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start infrastructure (Kafka + Zookeeper + OPA)
docker compose -f docker/docker-compose.yml up -d

# 5. Launch API
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

With Pre-Trained Model

```bash
# Generate synthetic training data and train RandomForest
python scripts/generate_clickstream.py
python scripts/train_model.py
# Saves models/intent_classifier.joblib for ML ensemble fallback
```

## 🔬 API Reference

Interactive Documentation
Once running, visit: http://localhost:8000/docs

Endpoints
#### \\\\

Example Request
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

Example Response (Intent Prediction)
```JSON
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
  "predicted_next_state": "PURCHASE",
  "generated_at": "2024-01-15T10:30:00Z"
}
```
## Synthetic Data Generation 

Generated 34148 events across 5000 sessions → data/synthetic_clicks.csv
shape: (7, 2)
┌─────────────────────┬──────┐
│ ground_truth_intent ┆ len  │
│ ---                 ┆ ---  │
│ str                 ┆ u32  │
╞═════════════════════╪══════╡
│ BROWSE              ┆ 7180 │
│ PRICE_SENSITIVE     ┆ 7070 │
│ COMPARE             ┆ 6880 │
│ CART_BUILDER        ┆ 5824 │
│ CHECKOUT_INTENT     ┆ 3610 │
│ LOYAL_RETURNER      ┆ 2130 │
│ CHURN_RISK          ┆ 1454 │
└─────────────────────┴──────┘
                 precision    recall  f1-score   support

         BROWSE       1.00      1.00      1.00       144
   CART_BUILDER       1.00      1.00      1.00       146
CHECKOUT_INTENT       1.00      1.00      1.00       144
     CHURN_RISK       1.00      1.00      1.00       145
        COMPARE       1.00      1.00      1.00       138
 LOYAL_RETURNER       1.00      1.00      1.00       142
PRICE_SENSITIVE       1.00      1.00      1.00       141

       accuracy                           1.00      1000
      macro avg       1.00      1.00      1.00      1000
   weighted avg       1.00      1.00      1.00      1000

Model saved to models/intent_classifier.joblib


## 🧪 Test

```bash
# Run full test suite
pytest tests/ -v --cov=src --cov-report=term-missing

# Expected: 84+ tests, 70%+ coverage
```

## 🔒 Safety & Governance

- Anti-gaming: No duplicate discounts within 15 minutes; max 3 discounts/month per customer
- Fairness guardrail: No demographic-based pricing discrimination (OPA policy + Python fallback)
- Audit trail: Immutable ledger of every action dispatched with intent, confidence, and reason
- Deterministic fallback: Rule-based classifier always available; ML model is optional enhancement

## 🤝 Contributing

This is an active portfolio project. Contributions welcome in:
- Additional intent classes (BARGAIN_HUNTER, GIFT_SHOPPER)
- Real-time bidding (RTB) integration patterns
- Multi-modal intent (image search, voice queries)
- Reinforcement learning for action optimization

📄 License
MIT License — AI Engineering Portfolio
---

<p align="center">
  <sub>Built with FastAPI, Polars, Kafka, and a deep respect for deterministic reasoning.</sub>
</p>

