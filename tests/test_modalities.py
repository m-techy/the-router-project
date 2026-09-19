from pathlib import Path

import httpx
import pytest

from app.modalities import (
    EMBEDDING_MODELS,
    TRANSCRIPTION_MODELS,
    ModalityRouter,
    embedding_requirements,
    normalize_embedding_encoding,
)
from app.models import EmbeddingRequest, TierType
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.router import FreeRouter
from app.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


def make_router(tmp_path):
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "router.db")
    chat = FreeRouter(registry, QuotaManager(store))
    return registry, store, ModalityRouter(chat)


def test_new_provider_tiers_are_fail_safe():
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")

    assert registry.get("vercel-ai-gateway").tier == TierType.PERSISTENT_FREE
    assert registry.get("huggingface").tier == TierType.PERSISTENT_FREE
    assert registry.get("pollinations").tier == TierType.PROMOTIONAL

    default_ids = {
        provider.id
        for provider in registry.allowed_providers(
            allow_trial=False,
            allow_promo=False,
        )
    }
    promo_ids = {
        provider.id
        for provider in registry.allowed_providers(
            allow_trial=False,
            allow_promo=True,
        )
    }

    assert "vercel-ai-gateway" in default_ids
    assert "huggingface" in default_ids
    assert "pollinations" not in default_ids
    assert "pollinations" in promo_ids


def test_embedding_aliases_and_transcription_aliases_are_separate():
    assert "embed/auto" in EMBEDDING_MODELS
    assert "embed/multimodal" in EMBEDDING_MODELS
    assert "transcribe/auto" in TRANSCRIPTION_MODELS
    assert EMBEDDING_MODELS.isdisjoint(TRANSCRIPTION_MODELS)


def test_embedding_requirements_detect_inline_modalities():
    request = [
        {"type": "text", "text": "Represent this image"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,aGVsbG8="},
        },
        {
            "type": "input_audio",
            "input_audio": {"format": "wav", "data": "aGVsbG8="},
        },
    ]

    assert embedding_requirements(request) == {"embeddings", "vision", "audio"}


def test_plain_embedding_routes_to_google_and_cloudflare(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    registry, store, router = make_router(tmp_path)

    candidates = router.embedding_candidates(
        EmbeddingRequest(model="embed/text", input="hello world"),
        allow_trial=False,
        allow_promo=False,
    )
    pairs = {(candidate.provider_id, candidate.model_id) for candidate in candidates}

    assert ("google-ai", "gemini-embedding-2") in pairs
    assert ("cloudflare-ai", "@cf/baai/bge-m3") in pairs
    assert ("cloudflare-ai", "@cf/qwen/qwen3-embedding-0.6b") in pairs
    assert not any(model_id == "gemini-3.8-flash" for _, model_id in pairs)
    store.close()


def test_multimodal_embedding_excludes_text_only_models(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    _, store, router = make_router(tmp_path)

    request = EmbeddingRequest(
        model="embed/multimodal",
        input=[
            {"type": "text", "text": "Represent this"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,aGVsbG8="},
            },
        ],
    )
    candidates = router.embedding_candidates(
        request,
        allow_trial=False,
        allow_promo=False,
    )

    assert candidates
    assert all(candidate.provider_id == "google-ai" for candidate in candidates)
    assert all(candidate.model_id == "gemini-embedding-2" for candidate in candidates)
    store.close()


def test_transcription_routes_only_to_transcription_models(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    _, store, router = make_router(tmp_path)

    candidates = router.transcription_candidates(
        "transcribe/auto",
        allow_trial=False,
        allow_promo=False,
    )
    pairs = {(candidate.provider_id, candidate.model_id) for candidate in candidates}

    assert ("groq", "whisper-large-v3-turbo") in pairs
    assert ("groq", "whisper-large-v3") in pairs
    assert not any(model_id == "openai/gpt-oss-120b" for _, model_id in pairs)
    store.close()


def test_embedding_base64_encoding_is_openai_compatible():
    body = {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": [0.25, -0.5, 1.0],
            }
        ],
    }

    encoded = normalize_embedding_encoding(body, "base64")
    assert isinstance(encoded["data"][0]["embedding"], str)
    assert encoded["data"][0]["embedding"]


def test_image_generation_capability_is_registered():
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    cloudflare = registry.get("cloudflare-ai")
    image_models = [
        model for model in cloudflare.models if model.capabilities.image_generation
    ]

    assert any(model.id == "@cf/black-forest-labs/flux-1-schnell" for model in image_models)
    assert all(not model.capabilities.chat for model in image_models)


@pytest.mark.asyncio
async def test_embedding_request_returns_openai_shape_with_router_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    _, store, router = make_router(tmp_path)

    async def fake_embeddings(provider, model, request):
        return {
            "object": "list",
            "data": [
                {
                    "object": "embedding",
                    "index": 0,
                    "embedding": [0.1, 0.2, 0.3],
                }
            ],
            "model": model,
            "usage": {"prompt_tokens": 3, "total_tokens": 3},
        }, httpx.Headers()

    router.chat_router.adapters["gemini_hybrid"].embeddings = fake_embeddings

    routed = await router.embeddings(
        EmbeddingRequest(model="embed/auto", input="hello"),
        allow_trial=False,
        allow_promo=False,
    )

    assert routed.provider == "google-ai"
    assert routed.body["object"] == "list"
    assert routed.body["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert routed.body["router"]["provider"] == "google-ai"
    store.close()


@pytest.mark.asyncio
async def test_transcription_request_uses_groq_whisper(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    _, store, router = make_router(tmp_path)

    async def fake_transcription(provider, model, **kwargs):
        assert kwargs["filename"] == "sample.wav"
        assert kwargs["data"] == b"audio-bytes"
        return (
            b'{"text":"hello"}',
            httpx.Headers({"content-type": "application/json"}),
            "application/json",
        )

    router.chat_router.adapters["openai_compatible"].transcription = fake_transcription

    routed = await router.transcription(
        requested_model="transcribe/auto",
        filename="sample.wav",
        data=b"audio-bytes",
        content_type="audio/wav",
        language=None,
        prompt=None,
        response_format="json",
        temperature=None,
        allow_trial=False,
        allow_promo=False,
    )

    assert routed.provider == "groq"
    assert routed.model in {"whisper-large-v3", "whisper-large-v3-turbo"}
    assert routed.content == b'{"text":"hello"}'
    store.close()
