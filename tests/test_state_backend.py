from pathlib import Path

import pytest

import app.state_backend as state_backend


def test_sqlite_remains_default_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("ROUTER_STATE_BACKEND", raising=False)
    store = state_backend.create_state_store(tmp_path / "router.db")
    try:
        assert state_backend.state_backend_info(store) == {
            "backend": "sqlite",
            "durable": True,
            "serverless_safe": False,
        }
    finally:
        store.close()


def test_postgres_backend_fails_closed_without_connection_url(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTER_STATE_BACKEND", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL_NON_POOLING", raising=False)

    with pytest.raises(RuntimeError, match="requires DATABASE_URL"):
        state_backend.create_state_store(tmp_path / "ignored.db")


def test_unknown_backend_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTER_STATE_BACKEND", "redis")

    with pytest.raises(RuntimeError, match="Unsupported ROUTER_STATE_BACKEND"):
        state_backend.create_state_store(tmp_path / "ignored.db")
