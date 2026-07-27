from src.execution.base import BaseActionLedger

_action_ledger: BaseActionLedger | None = None


def get_action_ledger() -> BaseActionLedger:
    global _action_ledger
    if _action_ledger is None:
        from src.config import settings

        if settings.use_pg_ledger:
            from src.execution.pg_ledger import PGActionLedger

            _action_ledger = PGActionLedger(dsn=settings.postgres_dsn)
        else:
            from src.execution.sqlite_ledger import SQLiteActionLedger

            _action_ledger = SQLiteActionLedger(
                db_path=settings.database_url.replace("sqlite:///", "")
            )
    return _action_ledger


async def close_ledger() -> None:
    global _action_ledger
    if _action_ledger:
        await _action_ledger.close()
        _action_ledger = None
