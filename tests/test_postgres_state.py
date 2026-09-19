import os

import pytest

from app.project_keys import ProjectCreate, authenticate_project, create_project_key
from app.state_backend import state_backend_info
from app.state_postgres import PostgresStateStore
from app.vault import generate_key

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL is not configured",
)


@pytest.fixture
def postgres_store(monkeypatch):
    monkeypatch.setenv("ROUTER_VAULT_KEY", generate_key())
    store = PostgresStateStore(os.environ["TEST_POSTGRES_URL"])
    store._conn.execute(
        """
        TRUNCATE TABLE
          project_usage,
          project_keys,
          usage_events,
          model_runtime,
          provider_runtime,
          settings,
          local_secrets
        RESTART IDENTITY CASCADE
        """
    )
    yield store
    store._conn.execute(
        """
        TRUNCATE TABLE
          project_usage,
          project_keys,
          usage_events,
          model_runtime,
          provider_runtime,
          settings,
          local_secrets
        RESTART IDENTITY CASCADE
        """
    )
    store.close()


def test_postgres_backend_is_serverless_safe(postgres_store):
    info = state_backend_info(postgres_store)
    assert info == {
        "backend": "postgres",
        "durable": True,
        "serverless_safe": True,
    }


def test_postgres_usage_runtime_and_trace_round_trip(postgres_store):
    postgres_store.record_usage(
        ts=1000.0,
        request_id="router-pg",
        provider_id="groq",
        model_id="model-a",
        success=1,
        status_code=200,
        prompt_tokens=3,
        completion_tokens=4,
        total_tokens=7,
        latency_ms=12.5,
        fallback_count=0,
        error=None,
    )
    rows = postgres_store.request_trace("router-pg")
    assert len(rows) == 1
    assert rows[0]["provider_id"] == "groq"
    assert rows[0]["total_tokens"] == 7
    assert rows[0]["success"] is True

    postgres_store.upsert_runtime(
        "groq",
        successes=4,
        failures=1,
        latency_ema_ms=20.0,
        certification_state="active",
        provider_quota_json={"requests_remaining": 10},
    )
    runtime = postgres_store.get_runtime("groq")
    assert runtime["successes"] == 4
    assert runtime["certification_state"] == "active"
    assert "requests_remaining" in runtime["provider_quota_json"]

    postgres_store.upsert_model_runtime(
        "groq",
        "model-a",
        successes=3,
        failures=1,
        blocked_until=0,
    )
    model = postgres_store.get_model_runtime("groq", "model-a")
    assert model["successes"] == 3


def test_postgres_encrypts_secrets_at_rest(postgres_store):
    postgres_store.set_secret("GROQ_API_KEY", "hosted-secret")
    assert postgres_store.get_secret("GROQ_API_KEY") == "hosted-secret"

    raw = postgres_store._conn.execute(
        "SELECT value FROM local_secrets WHERE key=%s",
        ("GROQ_API_KEY",),
    ).fetchone()["value"]
    assert raw.startswith("fernet:")
    assert "hosted-secret" not in raw

    status = postgres_store.vault_status()
    assert status["enabled"] is True
    assert status["encrypted_secrets"] == 1


def test_postgres_settings_and_projects_round_trip(postgres_store):
    postgres_store.set_setting("routing", {"mode": "strict"})
    assert postgres_store.get_setting("routing") == {"mode": "strict"}

    created = create_project_key(
        postgres_store,
        ProjectCreate(
            name="hosted-client",
            daily_request_limit=5,
            daily_token_limit=1000,
        ),
    )
    project = authenticate_project(
        postgres_store,
        f"Bearer {created['key']}",
    )
    assert project is not None
    assert project["name"] == "hosted-client"

    postgres_store.record_project_usage(
        project["id"],
        requests=2,
        tokens=120,
    )
    assert postgres_store.project_usage_today(project["id"]) == {
        "requests": 2,
        "tokens": 120,
    }

    assert postgres_store.delete_project(project["id"]) is True
    assert authenticate_project(
        postgres_store,
        f"Bearer {created['key']}",
    ) is None
