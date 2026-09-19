from app.normalization import (
    drop_orphan_tool_messages,
    normalize_request_body,
)


def test_mistral_strips_rejected_fields_and_clamps_temperature():
    body = {
        "model": "mistral",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 1.7,
        "parallel_tool_calls": True,
        "metadata": {"x": 1},
        "stream": False,
        "stream_options": {"include_usage": True},
    }
    normalized = normalize_request_body("mistral", body)
    assert normalized["temperature"] == 1
    assert "parallel_tool_calls" not in normalized
    assert "metadata" not in normalized
    assert "stream_options" not in normalized
    assert body["temperature"] == 1.7


def test_zai_drops_only_orphan_tool_results():
    body = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call-1", "type": "function", "function": {"name": "a"}},
                    {"id": "call-2", "type": "function", "function": {"name": "b"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "one"},
            {"role": "tool", "tool_call_id": "call-2", "content": "two"},
            {"role": "tool", "tool_call_id": "missing", "content": "orphan"},
            {"role": "user", "content": "continue"},
        ]
    }
    normalized = normalize_request_body("zai", body)
    tool_ids = [
        message["tool_call_id"]
        for message in normalized["messages"]
        if message.get("role") == "tool"
    ]
    assert tool_ids == ["call-1", "call-2"]


def test_normalizer_leaves_other_providers_untouched():
    body = {"messages": [{"role": "user", "content": "hi"}], "metadata": {"keep": True}}
    assert normalize_request_body("groq", body) is body


def test_tool_without_id_is_removed():
    body = {"messages": [{"role": "tool", "content": "bad"}]}
    normalized = drop_orphan_tool_messages(body)
    assert normalized["messages"] == []
