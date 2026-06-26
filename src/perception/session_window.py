from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class SessionWindow:
    """Manages sliding windows and session timeouts."""

    def __init__(self, timeout_minutes: Optional[int] = None):
        self.timeout_minutes = timeout_minutes or settings.session_timeout_minutes
        self._sessions: Dict[str, List[ClickEvent]] = {}
        self._last_seen: Dict[str, datetime] = {}

    def add_event(self, event: ClickEvent) -> List[ClickEvent]:
        """Add event to session. Returns expired session events if timeout triggered."""
        expired = []
        session_id = event.session_id

        # Check for expired sessions
        now = event.timestamp
        expired_sessions = [
            sid
            for sid, last in self._last_seen.items()
            if now - last > timedelta(minutes=self.timeout_minutes)
        ]
        for sid in expired_sessions:
            expired.extend(self._sessions.pop(sid, []))
            self._last_seen.pop(sid, None)
            logger.debug(f"Session expired: {sid}")

        # Add to current session
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(event)
        self._last_seen[session_id] = now

        return expired

    def get_session(self, session_id: str) -> List[ClickEvent]:
        return self._sessions.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._last_seen.pop(session_id, None)
