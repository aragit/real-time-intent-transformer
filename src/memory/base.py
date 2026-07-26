from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from src.models.events import ClickEvent


class BaseSessionStore(ABC):
    """Abstract base class for session storage backends."""

    @abstractmethod
    async def upsert(self, session_id: str, customer_id: Optional[str], ttl_hours: int = 24) -> None:
        """Create or update a session with TTL."""
        ...

    @abstractmethod
    async def get(self, session_id: str) -> Optional[dict]:
        """Retrieve a session by ID. Returns None if not found or expired."""
        ...

    @abstractmethod
    async def delete_expired(self) -> int:
        """Remove all expired sessions. Returns count of deleted sessions."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying connection."""
        ...


class BaseEventStore(ABC):
    """Abstract base class for event storage backends."""

    @abstractmethod
    async def insert(self, event: ClickEvent) -> None:
        """Insert or replace an event."""
        ...

    @abstractmethod
    async def get_session_events(self, session_id: str) -> List[ClickEvent]:
        """Retrieve all events for a session, ordered by timestamp."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying connection."""
        ...
