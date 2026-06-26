from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency")

# Business metrics
EVENTS_INGESTED = Counter("events_ingested_total", "Total click events ingested")
INTENT_PREDICTIONS = Counter("intent_predictions_total", "Intent predictions by class", ["intent"])
ACTIONS_DISPATCHED = Counter("actions_dispatched_total", "Actions dispatched by type", ["action"])
ACTIONS_SUPPRESSED = Counter("actions_suppressed_total", "Actions suppressed")

# Session metrics
ACTIVE_SESSIONS = Gauge("active_sessions", "Currently active sessions")
