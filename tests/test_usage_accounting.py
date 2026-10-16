from app.models import ChatCompletionRequest, ChatMessage
from app.router import usage_from_body


def request():
    return ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="hello world")],
    )


def test_usage_from_body_preserves_provider_usage():
    body = {
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 4,
            "total_tokens": 12,
        },
    }

    assert usage_from_body(body, request()) == (8, 4, 12)


def test_usage_from_body_estimates_when_provider_omits_usage():
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": "hello there"}},
        ],
    }

    prompt, completion, total = usage_from_body(body, request())

    assert prompt == 2
    assert completion == 3
    assert total == prompt + completion


def test_usage_from_body_estimates_only_missing_components():
    body = {
        "usage": {"prompt_tokens": 7},
        "choices": [
            {"message": {"role": "assistant", "content": "hello there"}},
        ],
    }

    assert usage_from_body(body, request()) == (7, 3, 10)
