from abc import ABC, abstractmethod

from src.models.actions import ActionDispatch


class BaseActionLedger(ABC):
    """Abstract base class for action ledger storage backends."""

    @abstractmethod
    async def record(self, dispatch: ActionDispatch) -> None:
        """Record an action dispatch to the ledger."""
        ...

    @abstractmethod
    async def get_history(self, session_id: str) -> list[ActionDispatch]:
        """Retrieve all dispatched actions for a session, most recent first."""
        ...

    @abstractmethod
    async def get_by_id(self, action_id: str) -> ActionDispatch | None:
        """Retrieve a single action dispatch by its ID."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying connection pool."""
        ...
