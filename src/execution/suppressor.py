from datetime import datetime, timedelta
from typing import Dict, Optional

from loguru import logger


class ActionSuppressor:
    """Prevents duplicate actions within a time window per session."""

    def __init__(self, cooldown_minutes: int = 15):
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._last_action: Dict[str, datetime] = {}
        self._action_counts: Dict[str, int] = {}

    def can_dispatch(self, session_id: str, action: str) -> bool:
        key = f"{session_id}:{action}"
        last = self._last_action.get(key)
        now = datetime.utcnow()
        if last and (now - last) < self.cooldown:
            logger.debug(f"Suppressed {action} for {session_id}: cooldown active")
            return False
        return True

    def record(self, session_id: str, action: str) -> None:
        key = f"{session_id}:{action}"
        self._last_action[key] = datetime.utcnow()
        self._action_counts[key] = self._action_counts.get(key, 0) + 1

    def get_count(self, session_id: str, action: str) -> int:
        return self._action_counts.get(f"{session_id}:{action}", 0)

    def clear_session(self, session_id: str) -> None:
        keys = [k for k in self._last_action if k.startswith(f"{session_id}:")]
        for k in keys:
            self._last_action.pop(k, None)
            self._action_counts.pop(k, None)
