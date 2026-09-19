import base64

import httpx
import pytest

import app.main as main
from app.modalities import RoutedImage
from app.router import RoutedResponse


@pytest.fixture(autouse=True)
def local_routing_mode(monkeypatch):
    monkeypatch.setattr(main, "IS_VERCEL", False)
    monkeypatch.setenv("ROUTER_REQUIRE_PROJECT_KEYS", "false")
    monkeypatch.delenv("ROUTER_ENABLE_HOSTED_API", raising=False)


@pytest.mark.asyncio
async def test_responses_endpoint_returns_response_shape_and_route_headers(monkeypatch):
    async def fake_chat(request, *, allow_trial, allow_promo):
        return RoutedResponse(
            body={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "routed answer",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 2,
                    "total_tokens": 6,
                },
                "router": {"request_id": "router-test"},
            },
            provider="groq",
            model="model-a",
            fallback_count=1,
            route_reason="test-route",
        )

    monkeypatch.setattr(main.router, "chat", fake_chat)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "free/auto",
                "instructions": "Be short.",
                "input": "hello",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "response"
    assert body["output_text"] == "routed answer"
    assert body["router"]["provider"] == "groq"
    assert response.headers["x-router-provider"] == "groq"
    assert response.headers["x-router-fallback-count"] == "1"


@pytest.mark.asyncio
async def test_responses_stream_with_tools_is_rejected_before_routing(monkeypatch):
    async def should_not_stream(*args, **kwargs):
        raise AssertionError("router.stream should not be called")

    monkeypatch.setattr(main.router, "stream", should_not_stream)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "free/auto",
                "input": "hello",
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert "function-tool deltas" in response.json()["detail"]


@pytest.mark.asyncio
async def test_images_endpoint_returns_routed_base64_and_headers(monkeypatch):
    image = base64.b64encode(b"fake-image").decode()

    async def fake_image(request, *, allow_trial, allow_promo):
        return RoutedImage(
            body={
                "created": 1,
                "data": [{"b64_json": image}],
                "router": {"request_id": "image-test"},
            },
            provider="cloudflare-ai",
            model="@cf/black-forest-labs/flux-1-schnell",
            fallback_count=0,
            route_reason="image-test",
        )

    monkeypatch.setattr(main.modalities, "image_generation", fake_image)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={
                "model": "image/auto",
                "prompt": "a tiny robot",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"][0]["b64_json"] == image
    assert response.headers["x-router-provider"] == "cloudflare-ai"


@pytest.mark.asyncio
async def test_images_endpoint_rejects_unknown_fields():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={
                "model": "image/auto",
                "prompt": "a tiny robot",
                "partial_images": 2,
            },
        )

    assert response.status_code == 422
