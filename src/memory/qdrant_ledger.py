"""
Episodic Memory Ledger (Qdrant)
================================
Stores governance decisions (intent → action → verdict) as vector embeddings
in a Qdrant collection. Embeddings are generated via the local Ollama backend
so the system can later perform similarity searches over past decision traces.

This gives the architecture a "memory of failures" — blocked hallucinations
and denied actions are retained for downstream meta-cognition and drift
detection.
"""

import uuid
from datetime import UTC, datetime

import httpx
from loguru import logger
from qdrant_client import QdrantClient, models

from src.config import settings

COLLECTION_NAME = "episodic_memory"
EMBEDDING_DIM = 384


def _build_summary(
    session_id: str,
    intent: str,
    proposed_action: str,
    opa_verdict: str,
) -> str:
    """Build a human-readable interaction summary for embedding."""
    return (
        f"User exhibited {intent} intent. "
        f"SLM proposed {proposed_action}. "
        f"OPA verdict: {opa_verdict}."
    )


class QdrantEpisodicMemory:
    """Async wrapper around Qdrant for episodic decision memory."""

    def __init__(
        self,
        qdrant_url: str | None = None,
        ollama_base_url: str | None = None,
        embedding_model: str = "nomic-embed-text",
    ):
        self._qdrant_url = qdrant_url or "http://localhost:6333"
        self._ollama_base_url = (ollama_base_url or settings.llm_base_url).rstrip(
            "/v1"
        ).rstrip("/")
        self._embedding_model = embedding_model
        self._client: QdrantClient | None = None
        self._http_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self._qdrant_url, timeout=10)
        return self._client

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def initialise(self) -> None:
        """Create the collection if it doesn't already exist."""
        client = await self._get_client()
        collections = client.get_collections()
        existing = {c.name for c in collections.collections}
        if COLLECTION_NAME not in existing:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection '{COLLECTION_NAME}'")
        else:
            logger.debug(f"Qdrant collection '{COLLECTION_NAME}' already exists")

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._client = None
        self._http_client = None

    # ------------------------------------------------------------------
    # Embedding via Ollama
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Generate a vector embedding from the local Ollama embedding model."""
        http = await self._get_http()
        url = f"{self._ollama_base_url}/api/embed"
        payload = {
            "model": self._embedding_model,
            "input": text,
        }
        try:
            resp = await http.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise RuntimeError("Ollama returned empty embeddings")
            return embeddings[0]
        except Exception:
            logger.error(
                f"Ollama embedding failed for model '{self._embedding_model}':\n"
                f"{__import__('traceback').format_exc()}"
            )
            raise

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    async def store_decision(
        self,
        session_id: str,
        intent: str,
        proposed_action: str,
        opa_verdict: str,
    ) -> str:
        """Embed the decision summary and upsert it into Qdrant.

        Returns the generated point ID.
        """
        summary = _build_summary(session_id, intent, proposed_action, opa_verdict)
        vector = await self._embed(summary)

        point_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        client = await self._get_client()
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "session_id": session_id,
                        "intent": intent,
                        "proposed_action": proposed_action,
                        "opa_verdict": opa_verdict,
                        "summary": summary,
                        "timestamp": now,
                    },
                )
            ],
        )
        logger.info(
            f"Stored episodic memory: session={session_id} "
            f"intent={intent} action={proposed_action} verdict={opa_verdict} "
            f"point_id={point_id}"
        )
        return point_id


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_ledger: QdrantEpisodicMemory | None = None


def get_episodic_memory() -> QdrantEpisodicMemory:
    global _ledger
    if _ledger is None:
        _ledger = QdrantEpisodicMemory()
    return _ledger


async def close_episodic_memory() -> None:
    global _ledger
    if _ledger:
        await _ledger.close()
        _ledger = None
