import httpx
import pytest

from app.models import ChatCompletionRequest, ChatMessage
from app.providers.base import ProviderError
from app.providers.gemini import (
    GeminiHybridAdapter,
    _embedding_contents,
    build_native_payload,
    native_response_to_openai,
)
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.router import FreeRouter
from app.state import StateStore


def test_native_payload_maps_system_tools_json_and_tool_response():
    request = ChatCompletionRequest(
        messages=[
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Weather in Hyderabad?"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": "call_weather",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city":"Hyderabad"}',
                        },
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                tool_call_id="call_weather",
                content='{"temperature":31}',
            ),
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the weather.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
        tool_choice="required",
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=128,
    )

    payload = build_native_payload(request)

    assert payload["systemInstruction"]["parts"][0]["text"] == "Be concise."
    assert payload["tools"][0]["functionDeclarations"][0]["name"] == "get_weather"
    assert payload["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["maxOutputTokens"] == 128

    tool_response = payload["contents"][-1]["parts"][0]["functionResponse"]
    assert tool_response["name"] == "get_weather"
    assert tool_response["response"]["temperature"] == 31


def test_native_payload_maps_inline_image():
    request = ChatCompletionRequest(
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe this."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,aGVsbG8="
                        },
                    },
                ],
            )
        ]
    )

    payload = build_native_payload(request)
    parts = payload["contents"][0]["parts"]

    assert parts[0]["text"] == "Describe this."
    assert parts[1]["inlineData"]["mimeType"] == "image/png"
    assert parts[1]["inlineData"]["data"] == "aGVsbG8="


def test_embedding_normalizer_maps_text_image_and_audio_parts():
    contents = _embedding_contents(
        [
            {"type": "text", "text": "Represent this scene"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,aGVsbG8="
                },
            },
            {
                "type": "input_audio",
                "input_audio": {
                    "format": "wav",
                    "data": "aGVsbG8=",
                },
            },
        ]
    )

    assert len(contents) == 1
    parts = contents[0]
    assert parts[0]["text"] == "Represent this scene"
    assert parts[1]["inlineData"]["mimeType"] == "image/png"
    assert parts[1]["inlineData"]["data"] == "aGVsbG8="
    assert parts[2]["inlineData"]["mimeType"] == "audio/wav"


def test_embedding_normalizer_treats_string_list_as_batch():
    contents = _embedding_contents(["first", "second", "third"])

    assert len(contents) == 3
    assert [item[0]["text"] for item in contents] == ["first", "second", "third"]


def test_native_response_maps_text_tools_and_usage():
    response = native_response_to_openai(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "I will check. "},
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"city": "Hyderabad"},
                                }
                            },
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 5,
                "totalTokenCount": 17,
            },
        },
        model="gemini-test",
    )

    message = response["choices"][0]["message"]
    assert message["content"] == "I will check. "
    assert message["tool_calls"][0]["function"]["name"] == "get_weather"
    assert '"city":"Hyderabad"' in message["tool_calls"][0]["function"]["arguments"]
    assert response["usage"]["total_tokens"] == 17


@pytest.mark.asyncio
async def test_hybrid_falls_back_to_native_on_compatibility_error():
    client = httpx.AsyncClient()
    adapter = GeminiHybridAdapter(client, lambda _: "test-key")

    async def compat_fail(*args, **kwargs):
        raise ProviderError("unsupported compatibility field", 400)

    async def native_ok(*args, **kwargs):
        return {"choices": [{"message": {"content": "ok"}}]}, httpx.Headers()

    adapter.openai.chat = compat_fail
    adapter.native.chat = native_ok

    provider = ProviderRegistry("config/providers.yaml").get("google-ai")
    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="hello")]
    )
    body, _ = await adapter.chat(provider, "gemini-test", request)

    assert body["choices"][0]["message"]["content"] == "ok"
    await client.aclose()


@pytest.mark.asyncio
async def test_hybrid_does_not_retry_native_on_rate_limit():
    client = httpx.AsyncClient()
    adapter = GeminiHybridAdapter(client, lambda _: "test-key")

    async def rate_limited(*args, **kwargs):
        raise ProviderError("quota", 429)

    adapter.openai.chat = rate_limited
    provider = ProviderRegistry("config/providers.yaml").get("google-ai")
    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="hello")]
    )

    with pytest.raises(ProviderError) as exc:
        await adapter.chat(provider, "gemini-test", request)

    assert exc.value.status_code == 429
    await client.aclose()


def test_google_provider_uses_hybrid_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    registry = ProviderRegistry("config/providers.yaml")
    store = StateStore(tmp_path / "router.db")
    router = FreeRouter(registry, QuotaManager(store))

    assert registry.get("google-ai").adapter == "gemini_hybrid"
    assert isinstance(router._adapter(registry.get("google-ai")), GeminiHybridAdapter)
