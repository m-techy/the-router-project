from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

UNSUPPORTED_COMMON = {
    "parallel_tool_calls",
    "n",
    "top_k",
    "logprobs",
    "echo",
    "user",
    "metadata",
    "prompt_cache_key",
    "store",
}


def strip_unsupported(body: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in body.items() if key not in UNSUPPORTED_COMMON}
    if result.get("stream") is not True:
        result.pop("stream_options", None)
    return result


def drop_orphan_tool_messages(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body

    filtered: list[Any] = []
    pending: set[str] = set()
    changed = False

    for message in messages:
        if not isinstance(message, dict):
            changed = True
            continue

        role = message.get("role")
        if role == "assistant":
            filtered.append(message)
            calls = message.get("tool_calls")
            pending = {
                call.get("id")
                for call in calls
                if isinstance(call, dict) and isinstance(call.get("id"), str)
            } if isinstance(calls, list) else set()
            continue

        if role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or call_id not in pending:
                changed = True
                continue
            pending.discard(call_id)
            filtered.append(message)
            continue

        pending = set()
        filtered.append(message)

    if not changed and len(filtered) == len(messages):
        return body
    result = dict(body)
    result["messages"] = filtered
    return result


def clamp_temperature(
    body: dict[str, Any],
    *,
    minimum: float = 0,
    maximum: float = 1,
) -> dict[str, Any]:
    value = body.get("temperature")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return body
    clamped = max(minimum, min(maximum, float(value)))
    if clamped == value:
        return body
    result = dict(body)
    result["temperature"] = clamped
    return result


def normalize_zai(body: dict[str, Any]) -> dict[str, Any]:
    return drop_orphan_tool_messages(strip_unsupported(body))


def normalize_mistral(body: dict[str, Any]) -> dict[str, Any]:
    result = strip_unsupported(body)
    result = clamp_temperature(result, minimum=0, maximum=1)
    return drop_orphan_tool_messages(result)


def normalize_nvidia(body: dict[str, Any]) -> dict[str, Any]:
    return drop_orphan_tool_messages(strip_unsupported(body))


NORMALIZERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "zai": normalize_zai,
    "mistral": normalize_mistral,
    "codestral": normalize_mistral,
    "nvidia": normalize_nvidia,
}


def normalize_request_body(provider_id: str, body: dict[str, Any]) -> dict[str, Any]:
    normalizer = NORMALIZERS.get(provider_id)
    if normalizer is None:
        return body
    # Provider normalization must never mutate the caller's request representation.
    return normalizer(deepcopy(body))
