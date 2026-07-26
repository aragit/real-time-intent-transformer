import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from loguru import logger
import redis.asyncio as aioredis

from src.memory.base import BaseSessionStore, BaseEventStore
from src.models.events import ClickEvent


class RedisSessionStore(BaseSessionStore):
    """Redis-backed session store using JSON serialization with automatic TTL."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("RedisSessionStore connected")
        return self._client

    async def upsert(self, session_id: str, customer_id: Optional[str], ttl_hours: int = 24) -> None:
        client = await self._get_client()
        now = datetime.now(timezone.utc)
        session_data = {
            "session_id": session_id,
            "customer_id": customer_id,
            "created_at": now.isoformat(),
            "last_activity": now.isoformat(),
            "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        }
        key = f"session:{session_id}"
        ttl_seconds = ttl_hours * 3600
        await client.setex(key, ttl_seconds, json.dumps(session_data))

    async def get(self, session_id: str) -> Optional[dict]:
        client = await self._get_client()
        key = f"session:{session_id}"
        data = await client.get(key)
        if data is None:
            return None
        session = json.loads(data)
        if datetime.fromisoformat(session["expires_at"]) < datetime.now(timezone.utc):
            await client.delete(key)
            return None
        return session

    async def delete_expired(self) -> int:
        client = await self._get_client()
        count = 0
        async for key in client.scan_iter("session:*"):
            data = await client.get(key)
            if data:
                session = json.loads(data)
                if datetime.fromisoformat(session["expires_at"]) < datetime.now(timezone.utc):
                    await client.delete(key)
                    count += 1
        return count

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class RedisEventStore(BaseEventStore):
    """Redis-backed event store using bounded lists per session (max 100 events)."""

    MAX_EVENTS_PER_SESSION = 100

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("RedisEventStore connected")
        return self._client

    async def insert(self, event: ClickEvent) -> None:
        client = await self._get_client()
        key = f"events:{event.session_id}"
        event_data = {
            "event_id": event.event_id,
            "session_id": event.session_id,
            "customer_id": event.customer_id,
            "timestamp": event.timestamp.isoformat(),
            "action": event.action,
            "product_id": event.product_id,
            "category": event.category,
            "value": event.value,
            "metadata": json.dumps(event.metadata) if event.metadata else "{}",
        }
        await client.lpush(key, json.dumps(event_data))
        await client.ltrim(key, 0, self.MAX_EVENTS_PER_SESSION - 1)

    async def get_session_events(self, session_id: str) -> List[ClickEvent]:
        client = await self._get_client()
        key = f"events:{session_id}"
        raw_events = await client.lrange(key, 0, -1)
        events = []
        for raw in reversed(raw_events):
            data = json.loads(raw)
            events.append(ClickEvent(
                event_id=data["event_id"],
                session_id=data["session_id"],
                customer_id=data.get("customer_id"),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                action=data["action"],
                product_id=data.get("product_id"),
                category=data.get("category"),
                value=data.get("value"),
                metadata=json.loads(data.get("metadata", "{}")),
            ))
        return events

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
