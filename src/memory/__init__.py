from src.memory.base import BaseEventStore, BaseSessionStore

_session_store: BaseSessionStore | None = None
_event_store: BaseEventStore | None = None


def get_session_store() -> BaseSessionStore:
    global _session_store
    if _session_store is None:
        from src.config import settings

        if settings.use_redis_store:
            from src.memory.redis_store import RedisSessionStore

            _session_store = RedisSessionStore(redis_url=settings.redis_url)
        else:
            from src.memory.sqlite_store import SQLiteSessionStore

            _session_store = SQLiteSessionStore(
                db_path=settings.database_url.replace("sqlite:///", "")
            )
    return _session_store


def get_event_store() -> BaseEventStore:
    global _event_store
    if _event_store is None:
        from src.config import settings

        if settings.use_redis_store:
            from src.memory.redis_store import RedisEventStore

            _event_store = RedisEventStore(redis_url=settings.redis_url)
        else:
            from src.memory.sqlite_store import SQLiteEventStore

            _event_store = SQLiteEventStore(db_path=settings.database_url.replace("sqlite:///", ""))
    return _event_store


async def close_stores() -> None:
    global _session_store, _event_store
    if _session_store:
        await _session_store.close()
        _session_store = None
    if _event_store:
        await _event_store.close()
        _event_store = None
