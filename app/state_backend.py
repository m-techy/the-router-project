from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .state import StateStore


def state_backend_name() -> str:
    return os.getenv("ROUTER_STATE_BACKEND", "sqlite").strip().lower()


def create_state_store(default_sqlite_path: str | Path) -> Any:
    backend = state_backend_name()

    if backend == "sqlite":
        return StateStore(default_sqlite_path)

    if backend == "postgres":
        dsn = (
            os.getenv("DATABASE_URL")
            or os.getenv("POSTGRES_URL")
            or os.getenv("POSTGRES_URL_NON_POOLING")
        )
        if not dsn:
            raise RuntimeError(
                "ROUTER_STATE_BACKEND=postgres requires DATABASE_URL, "
                "POSTGRES_URL, or POSTGRES_URL_NON_POOLING"
            )
        from .state_postgres import PostgresStateStore

        return PostgresStateStore(dsn)

    raise RuntimeError(
        f"Unsupported ROUTER_STATE_BACKEND={backend!r}; expected sqlite or postgres"
    )


def state_backend_info(store: Any) -> dict[str, Any]:
    return {
        "backend": getattr(store, "backend_name", "unknown"),
        "durable": bool(getattr(store, "durable", False)),
        "serverless_safe": bool(getattr(store, "serverless_safe", False)),
    }
