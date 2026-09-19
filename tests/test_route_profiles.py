from pathlib import Path

from app.models import ChatCompletionRequest, ChatMessage
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.route_profiles import (
    RouteProfile,
    delete_route_profile,
    load_route_profiles,
    route_model_id,
    save_route_profile,
)
from app.router import FreeRouter
from app.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


def make_router(tmp_path, monkeypatch):
    for key in [
        "GROQ_API_KEY",
        "CEREBRAS_API_KEY",
        "GOOGLE_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    store = StateStore(tmp_path / "routes.db")
    router = FreeRouter(
        ProviderRegistry(ROOT / "config" / "providers.yaml"),
        QuotaManager(store),
    )
    return router, store


def test_route_profile_round_trip(tmp_path):
    store = StateStore(tmp_path / "profiles.db")
    profile = RouteProfile(
        slug="my-app",
        name="My App",
        base_route="free/code",
        providers_allow=["kilo", "llm7", "kilo"],
        providers_deny=["ovhcloud"],
        min_context=32000,
        max_fallbacks=3,
    )

    save_route_profile(store, profile)
    loaded = load_route_profiles(store)

    assert loaded["my-app"].providers_allow == ["kilo", "llm7"]
    assert loaded["my-app"].max_fallbacks == 3
    assert route_model_id("my-app") == "route/my-app"
    assert delete_route_profile(store, "my-app") is True
    assert load_route_profiles(store) == {}
    store.close()


def test_custom_route_filters_provider_pool(tmp_path, monkeypatch):
    router, store = make_router(tmp_path, monkeypatch)
    save_route_profile(
        store,
        RouteProfile(
            slug="kilo-only",
            name="Kilo only",
            base_route="free/auto",
            providers_allow=["kilo"],
            max_fallbacks=2,
        ),
    )
    request = ChatCompletionRequest(
        model="route/kilo-only",
        messages=[ChatMessage(role="user", content="hello")],
    )

    candidates = router.candidates(
        request,
        allow_trial=False,
        allow_promo=False,
    )

    assert candidates
    assert {candidate.provider_id for candidate in candidates} == {"kilo"}
    assert router.max_attempts("route/kilo-only") == 2
    store.close()


def test_custom_route_base_strategy_drives_requirements(tmp_path, monkeypatch):
    router, store = make_router(tmp_path, monkeypatch)
    save_route_profile(
        store,
        RouteProfile(
            slug="vision-app",
            name="Vision app",
            base_route="free/vision",
        ),
    )
    request = ChatCompletionRequest(
        model="route/vision-app",
        messages=[ChatMessage(role="user", content="describe this")],
    )

    assert "vision" in router.resolved_requirements(request)
    store.close()


def test_unknown_custom_route_has_no_candidates(tmp_path, monkeypatch):
    router, store = make_router(tmp_path, monkeypatch)
    request = ChatCompletionRequest(
        model="route/does-not-exist",
        messages=[ChatMessage(role="user", content="hello")],
    )

    assert router.candidates(request, allow_trial=False, allow_promo=False) == []
    store.close()
