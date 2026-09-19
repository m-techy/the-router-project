import sqlite3

from app.project_keys import (
    ProjectCreate,
    authenticate_project,
    create_project_key,
    project_limit_state,
)
from app.state import StateStore
from app.vault import generate_key


def test_vault_encrypts_new_secrets_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTER_VAULT_KEY", generate_key())
    path = tmp_path / "vault.db"
    store = StateStore(path)

    store.set_secret("GROQ_API_KEY", "super-secret-value")
    assert store.get_secret("GROQ_API_KEY") == "super-secret-value"

    raw = store._conn.execute(
        "SELECT value FROM local_secrets WHERE key='GROQ_API_KEY'"
    ).fetchone()["value"]
    assert raw.startswith("fernet:")
    assert "super-secret-value" not in raw
    status = store.vault_status()
    assert status["enabled"] is True
    assert status["encrypted_secrets"] == 1
    store.close()


def test_enabling_vault_migrates_plaintext_on_read(tmp_path, monkeypatch):
    path = tmp_path / "migrate.db"
    monkeypatch.delenv("ROUTER_VAULT_KEY", raising=False)
    store = StateStore(path)
    store.set_secret("GOOGLE_API_KEY", "legacy-plaintext")
    store.close()

    monkeypatch.setenv("ROUTER_VAULT_KEY", generate_key())
    store = StateStore(path)
    assert store.get_secret("GOOGLE_API_KEY") == "legacy-plaintext"
    raw = store._conn.execute(
        "SELECT value FROM local_secrets WHERE key='GOOGLE_API_KEY'"
    ).fetchone()["value"]
    assert raw.startswith("fernet:")
    assert "legacy-plaintext" not in raw
    store.close()


def test_encrypted_secret_fails_closed_without_vault_key(tmp_path, monkeypatch):
    path = tmp_path / "locked.db"
    monkeypatch.setenv("ROUTER_VAULT_KEY", generate_key())
    store = StateStore(path)
    store.set_secret("TEST_KEY", "secret")
    store.close()

    monkeypatch.delenv("ROUTER_VAULT_KEY", raising=False)
    store = StateStore(path)
    assert store.get_secret("TEST_KEY") is None
    store.close()


def test_project_key_is_returned_once_and_only_hash_is_stored(tmp_path):
    store = StateStore(tmp_path / "projects.db")
    created = create_project_key(
        store,
        ProjectCreate(
            name="tech-trend-peek",
            daily_request_limit=25,
            daily_token_limit=10000,
        ),
    )

    assert created["key"].startswith("rtr_")
    project = authenticate_project(store, f"Bearer {created['key']}")
    assert project is not None
    assert project["name"] == "tech-trend-peek"

    row = store._conn.execute(
        "SELECT key_hash,key_prefix FROM project_keys WHERE id=?",
        (created["id"],),
    ).fetchone()
    assert created["key"] not in row["key_hash"]
    assert row["key_prefix"] == created["key"][:12]

    listed = store.list_projects()
    assert "key" not in listed[0]
    assert "key_hash" not in listed[0]
    store.close()


def test_project_daily_limits_use_separate_usage_ledger(tmp_path):
    store = StateStore(tmp_path / "limits.db")
    created = create_project_key(
        store,
        ProjectCreate(
            name="limited",
            daily_request_limit=2,
            daily_token_limit=100,
        ),
    )
    project = authenticate_project(store, f"Bearer {created['key']}")
    assert project is not None

    first = project_limit_state(store, project)
    assert first["request_limit_exhausted"] is False
    assert first["token_limit_exhausted"] is False

    store.record_project_usage(project["id"], requests=2, tokens=101)
    exhausted = project_limit_state(store, project)
    assert exhausted["request_limit_exhausted"] is True
    assert exhausted["token_limit_exhausted"] is True
    store.close()


def test_usage_cursor_supports_live_event_stream(tmp_path):
    store = StateStore(tmp_path / "events.db")
    store.record_usage(
        ts=1.0,
        request_id="router-one",
        provider_id="groq",
        model_id="model-a",
        success=1,
        status_code=200,
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        latency_ms=10.0,
        fallback_count=0,
        error=None,
    )
    first = store.usage_after_id(0)
    assert len(first) == 1
    assert first[0]["request_id"] == "router-one"
    assert store.usage_after_id(first[0]["id"]) == []
    store.close()


def test_config_settings_export_never_reads_secret_values(tmp_path):
    store = StateStore(tmp_path / "config.db")
    store.set_setting("example", {"enabled": True})
    store.set_secret("PRIVATE_KEY", "never-export-me")

    assert store.all_settings() == {"example": {"enabled": True}}
    assert store.secret_keys() == ["PRIVATE_KEY"]
    assert "never-export-me" not in str(store.all_settings())
    store.close()
