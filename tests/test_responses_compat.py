import json

import pytest

from app.models import ResponseCreateRequest
from app.responses_compat import (
    chat_body_to_response,
    chat_stream_to_responses,
    response_request_to_chat,
)


def test_responses_string_input_maps_to_chat():
    request = ResponseCreateRequest(
        model="free/auto",
        instructions="Be concise.",
        input="Hello",
        max_output_tokens=50,
    )

    chat = response_request_to_chat(request)

    assert chat.model == "free/auto"
    assert chat.messages[0].role == "system"
    assert chat.messages[0].content == "Be concise."
    assert chat.messages[1].role == "user"
    assert chat.messages[1].content == "Hello"
    assert chat.max_completion_tokens == 50


def test_responses_function_tool_maps_to_chat_tool():
    request = ResponseCreateRequest(
        input="weather",
        tools=[
            {
                "type": "function",
                "name": "weather",
                "description": "Get weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            }
        ],
        tool_choice={"type": "function", "name": "weather"},
    )

    chat = response_request_to_chat(request)

    assert chat.tools[0]["type"] == "function"
    assert chat.tools[0]["function"]["name"] == "weather"
    assert chat.tool_choice["function"]["name"] == "weather"


def test_responses_rejects_stateful_and_unsupported_builtin_tools():
    with pytest.raises(ValueError, match="previous_response_id"):
        response_request_to_chat(
            ResponseCreateRequest(input="hello", previous_response_id="resp_x")
        )

    with pytest.raises(ValueError, match="not supported"):
        response_request_to_chat(
            ResponseCreateRequest(
                input="search",
                tools=[{"type": "web_search"}],
            )
        )


def test_chat_body_converts_to_response_object():
    request = ResponseCreateRequest(input="hello")
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hi there",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        },
        "router": {"request_id": "router-123"},
    }

    response = chat_body_to_response(
        body,
        request,
        provider="groq",
        model="model-a",
    )

    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["output_text"] == "Hi there"
    assert response["output"][0]["content"][0]["type"] == "output_text"
    assert response["usage"]["total_tokens"] == 5
    assert response["router"]["provider"] == "groq"


@pytest.mark.asyncio
async def test_chat_stream_converts_text_deltas_to_response_events():
    async def upstream():
        yield b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    request = ResponseCreateRequest(input="hello", stream=True)
    chunks = [
        chunk.decode()
        async for chunk in chat_stream_to_responses(
            upstream(),
            request,
            provider="groq",
            model="model-a",
        )
    ]
    events = [
        json.loads(chunk.removeprefix("data: ").strip())
        for chunk in chunks
    ]
    types = [event["type"] for event in events]

    assert types[0] == "response.created"
    assert "response.output_text.delta" in types
    assert types[-1] == "response.completed"
    deltas = [
        event["delta"]
        for event in events
        if event["type"] == "response.output_text.delta"
    ]
    assert deltas == ["Hel", "lo"]
    assert events[-1]["response"]["output_text"] == "Hello"
