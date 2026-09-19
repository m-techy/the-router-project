import base64
from pathlib import Path

import httpx
import pytest
import respx

from app.modalities import ModalityRouter, image_neuron_estimate
from app.models import ImageGenerationRequest
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.router import FreeRouter
from app.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_cloudflare_flux_adapter_returns_openai_style_base64(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    provider = ProviderRegistry(ROOT / "config" / "providers.yaml").get("cloudflare-ai")
    image = base64.b64encode(b"fake-jpeg").decode()

    async with httpx.AsyncClient() as client:
        adapter = OpenAICompatibleAdapter(client)
        url = (
            "https://api.cloudflare.com/client/v4/accounts/acct/ai/run/"
            "@cf/black-forest-labs/flux-1-schnell"
        )
        with respx.mock:
            route = respx.post(url).mock(
                return_value=httpx.Response(
                    200,
                    json={"result": {"image": image}, "success": True},
                )
            )
            body, _ = await adapter.image_generation(
                provider,
                "@cf/black-forest-labs/flux-1-schnell",
                ImageGenerationRequest(
                    prompt="a tiny robot",
                    model="image/auto",
                ),
            )

    assert route.called
    sent = route.calls[0].request
    assert b'"prompt":"a tiny robot"' in sent.content
    assert body["data"][0]["b64_json"] == image


def test_image_route_selects_reviewed_cloudflare_flux(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    store = StateStore(tmp_path / "image.db")
    router = FreeRouter(registry, QuotaManager(store))
    modalities = ModalityRouter(router)
    request = ImageGenerationRequest(prompt="a tiny robot", model="image/auto")

    candidates = modalities.image_candidates(
        request,
        allow_trial=False,
        allow_promo=False,
    )

    assert candidates
    assert candidates[0].provider_id == "cloudflare-ai"
    assert candidates[0].model_id == "@cf/black-forest-labs/flux-1-schnell"
    assert image_neuron_estimate(request) == pytest.approx(43.2)
    store.close()


def test_cloudflare_image_route_stops_before_free_neuron_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    registry = ProviderRegistry(ROOT / "config" / "providers.yaml")
    provider = registry.get("cloudflare-ai")
    path = tmp_path / "neurons.db"
    store = StateStore(path)
    quota = QuotaManager(store)
    router = FreeRouter(registry, quota)
    modalities = ModalityRouter(router)
    request = ImageGenerationRequest(prompt="a tiny robot", model="image/auto")

    quota.record_neurons(provider.id, 9980)
    assert quota.snapshot(provider)["day_neurons"] == pytest.approx(9980)
    assert modalities.image_candidates(
        request,
        allow_trial=False,
        allow_promo=False,
    ) == []
    store.close()

    store = StateStore(path)
    restored = QuotaManager(store)
    assert restored.snapshot(provider)["day_neurons"] == pytest.approx(9980)
    store.close()


@pytest.mark.asyncio
async def test_cloudflare_flux_rejects_unsupported_size(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    provider = ProviderRegistry(ROOT / "config" / "providers.yaml").get("cloudflare-ai")

    async with httpx.AsyncClient() as client:
        adapter = OpenAICompatibleAdapter(client)
        with pytest.raises(Exception, match="image-size"):
            await adapter.image_generation(
                provider,
                "@cf/black-forest-labs/flux-1-schnell",
                ImageGenerationRequest(
                    prompt="a tiny robot",
                    model="image/auto",
                    size="1024x1024",
                ),
            )
