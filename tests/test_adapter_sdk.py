from collections.abc import AsyncIterator

import httpx
import pytest

from app.models import ChatCompletionRequest, ProviderSpec
from app.providers.base import AdapterCapabilities, ProviderAdapter
from app.providers.sdk import SDK_VERSION, validate_adapter
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.router import FreeRouter
from app.state import StateStore


class ExampleAdapter(ProviderAdapter):
    capabilities = AdapterCapabilities(embeddings=True)

    async def chat(self, provider, model, request):
        return {"choices": []}, httpx.Headers()

    async def stream(self, provider, model, request) -> AsyncIterator[bytes]:
        if False:
            yield b""
        return


class WrongVersionAdapter(ExampleAdapter):
    sdk_version = "0.9"


def test_sdk_version_and_capabilities_are_explicit():
    adapter = ExampleAdapter()
    assert SDK_VERSION == "1.0"
    assert adapter.supports("chat")
    assert adapter.supports("stream")
    assert adapter.supports("embeddings")
    assert not adapter.supports("transcription")


def test_sdk_rejects_wrong_version():
    with pytest.raises(ValueError, match="requires SDK"):
        validate_adapter("wrong", WrongVersionAdapter())


def test_router_can_register_custom_adapter(tmp_path):
    registry = ProviderRegistry("config/providers.yaml")
    store = StateStore(tmp_path / "router.db")
    router = FreeRouter(registry, QuotaManager(store))

    adapter = ExampleAdapter()
    router.register_adapter("example", adapter)

    assert router.adapters["example"] is adapter
    assert router.adapter_inventory()["example"]["sdk_version"] == "1.0"
    assert router.adapter_inventory()["example"]["capabilities"]["embeddings"] is True

    with pytest.raises(ValueError, match="already registered"):
        router.register_adapter("example", ExampleAdapter())

    store.close()
