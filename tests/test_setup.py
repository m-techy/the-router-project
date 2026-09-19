from pathlib import Path

from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.router import FreeRouter
from app.setup import provider_setup_status
from app.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


def test_saved_key_marks_provider_ready(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "router.db")

    before = {p["id"]: p for p in provider_setup_status(registry, store)}
    assert before["groq"]["ready"] is False

    store.set_secret("GROQ_API_KEY", "local-test-key")
    after = {p["id"]: p for p in provider_setup_status(registry, store)}
    assert after["groq"]["ready"] is True
    assert after["groq"]["requirements"][0]["source"] == "local"
    assert "local-test-key" not in str(after["groq"])
    store.close()


def test_environment_key_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-test-key")
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "router.db")
    store.set_secret("GROQ_API_KEY", "local-test-key")

    providers = {p["id"]: p for p in provider_setup_status(registry, store)}
    assert providers["groq"]["requirements"][0]["source"] == "environment"
    store.close()


def test_optional_key_provider_is_usable_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("KILO_API_KEY", raising=False)
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "router.db")
    providers = {p["id"]: p for p in provider_setup_status(registry, store)}

    assert providers["kilo"]["ready"] is True
    assert providers["kilo"]["no_key_required"] is True
    assert providers["kilo"]["requirements"][0]["optional"] is True
    store.close()


def test_router_uses_key_saved_in_local_store(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "router.db")
    store.set_secret("GROQ_API_KEY", "local-test-key")
    router = FreeRouter(registry, QuotaManager(store))

    assert router._provider_has_key(registry.get("groq")) is True
    assert (
        router.adapters["openai_compatible"]._api_key(registry.get("groq"))
        == "local-test-key"
    )
