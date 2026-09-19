import datetime as dt
from pathlib import Path
from app.models import ChatCompletionRequest, ChatMessage, TierType
from app.quota import QuotaManager
from app.registry import ProviderRegistry, model_is_current
from app.router import FreeRouter, request_requirements
from app.state import StateStore
ROOT=Path(__file__).resolve().parents[1]
def make_quota(tmp_path):return QuotaManager(StateStore(tmp_path/"test.db"))
def test_trial_provider_excluded_by_default(tmp_path):
    registry=ProviderRegistry(ROOT/"config"/"providers.yaml")
    ids={p.id for p in registry.allowed_providers(allow_trial=False,allow_promo=False)}
    assert "dashscope" not in ids and "groq" in ids and "kilo" in ids
    assert registry.get("dashscope").tier==TierType.TRIAL
def test_code_requirement_detection():
    req=ChatCompletionRequest(messages=[ChatMessage(role="user",content="Refactor this Python function")])
    assert "coding" in request_requirements(req)
def test_quota_blocks_at_rpm_limit(tmp_path):
    registry=ProviderRegistry(ROOT/"config"/"providers.yaml");p=registry.get("groq");p.quota.rpm=1;q=make_quota(tmp_path)
    assert q.available(p);q.record_success(p.id,model_id="test");assert not q.available(p)
def test_quota_survives_restart(tmp_path):
    registry=ProviderRegistry(ROOT/"config"/"providers.yaml");p=registry.get("openrouter");path=tmp_path/"persist.db"
    store=StateStore(path);q=QuotaManager(store);q.record_success(p.id,model_id="x",total_tokens=42);store.close()
    store=StateStore(path);snap=QuotaManager(store).snapshot(p);assert snap["day_requests"]==1 and snap["day_tokens"]==42;store.close()
def test_zai_prefix_is_internal_only(monkeypatch,tmp_path):
    monkeypatch.setenv("ZAI_API_KEY","test");registry=ProviderRegistry(ROOT/"config"/"providers.yaml");router=FreeRouter(registry,make_quota(tmp_path))
    assert router.adapters["openai_compatible"]._model_id(registry.get("zai"),"zai/glm-5.3-flash")=="glm-5.3-flash"
def test_no_key_providers_are_candidates(monkeypatch,tmp_path):
    for key in ["GROQ_API_KEY","CEREBRAS_API_KEY","GOOGLE_API_KEY","MISTRAL_API_KEY","OPENROUTER_API_KEY"]:monkeypatch.delenv(key,raising=False)
    router=FreeRouter(ProviderRegistry(ROOT/"config"/"providers.yaml"),make_quota(tmp_path));req=ChatCompletionRequest(messages=[ChatMessage(role="user",content="hello")])
    providers={c.provider_id for c in router.candidates(req,allow_trial=False,allow_promo=False)}
    assert {"kilo","llm7","ovhcloud"}.issubset(providers)
def test_promo_requires_opt_in(tmp_path,monkeypatch):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY","test");router=FreeRouter(ProviderRegistry(ROOT/"config"/"providers.yaml"),make_quota(tmp_path));req=ChatCompletionRequest(messages=[ChatMessage(role="user",content="hello")])
    normal={c.provider_id for c in router.candidates(req,allow_trial=False,allow_promo=False)}
    promo={c.provider_id for c in router.candidates(req,allow_trial=False,allow_promo=True)}
    assert "opencode-zen" not in normal and "opencode-zen" in promo


def test_broken_model_does_not_disable_whole_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    provider = registry.get("groq")
    enabled = [m for m in provider.models if m.enabled and m.free]
    assert len(enabled) >= 2
    quota = make_quota(tmp_path)
    router = FreeRouter(registry, quota)
    quota.record_failure(
        provider.id,
        model_id=enabled[0].id,
        status_code=404,
        error="model retired",
    )
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hello")])
    candidates = router.candidates(req, allow_trial=False, allow_promo=False)
    groq_models = {candidate.model_id for candidate in candidates if candidate.provider_id == "groq"}
    assert enabled[0].id not in groq_models
    assert enabled[1].id in groq_models
    assert quota.available(provider)


def test_model_runtime_survives_restart(tmp_path):
    path = tmp_path / "models.db"
    store = StateStore(path)
    quota = QuotaManager(store)
    quota.record_failure(
        "provider-x",
        model_id="retired-model",
        status_code=410,
        error="gone",
    )
    assert not quota.model_available("provider-x", "retired-model")
    store.close()

    store = StateStore(path)
    quota = QuotaManager(store)
    assert not quota.model_available("provider-x", "retired-model")
    assert quota.model_available("provider-x", "healthy-model")
    store.close()


def test_promotional_expiry_fails_closed():
    from app.models import ModelSpec

    now = dt.datetime(2026, 9, 19, tzinfo=dt.timezone.utc)
    active = ModelSpec(id="active", promotional_expires_at="2026-09-20T00:00:00Z")
    expired = ModelSpec(id="expired", promotional_expires_at="2026-09-18T00:00:00Z")
    malformed = ModelSpec(id="bad", promotional_expires_at="not-a-date")
    assert model_is_current(active, now)
    assert not model_is_current(expired, now)
    assert not model_is_current(malformed, now)
