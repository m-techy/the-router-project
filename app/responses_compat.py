from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from .models import ChatCompletionRequest, ChatMessage, ResponseCreateRequest


def _response_content_to_chat(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return content

    parts: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append({"type": "text", "text": str(item)})
            continue
        kind = item.get("type")
        if kind in {"input_text", "text"}:
            parts.append({"type": "text", "text": str(item.get("text") or "")})
        elif kind in {"input_image", "image_url"}:
            url = item.get("image_url")
            if isinstance(url, dict):
                url = url.get("url")
            if url:
                parts.append({"type": "image_url", "image_url": {"url": str(url)}})
                continue
            if item.get("file_id"):
                raise ValueError(
                    "Responses input_image file_id is not supported; provide image_url instead."
                )
            raise ValueError("Responses image input is missing image_url.")
        else:
            raise ValueError(f"Responses content part type {kind!r} is not supported.")
    return parts


def _response_tools_to_chat(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            raise ValueError(
                f"Responses tool type {tool.get('type')!r} is not supported by The Router."
            )
        if not tool.get("name"):
            raise ValueError("Responses function tool is missing name.")
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description"),
                    "parameters": tool.get("parameters") or {},
                    "strict": tool.get("strict"),
                },
            }
        )
    return converted


def _response_tool_choice_to_chat(choice: Any) -> Any:
    if choice is None or isinstance(choice, str):
        return choice
    if isinstance(choice, dict) and choice.get("type") == "function":
        name = choice.get("name")
        if name:
            return {"type": "function", "function": {"name": name}}
    return choice


def _response_format_to_chat(text: dict[str, Any] | None) -> dict[str, Any] | None:
    if not text:
        return None
    fmt = text.get("format")
    if not isinstance(fmt, dict):
        return None
    kind = fmt.get("type")
    if kind == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": fmt.get("name") or "response",
                "schema": fmt.get("schema") or {},
                "strict": fmt.get("strict", True),
            },
        }
    if kind == "json_object":
        return {"type": "json_object"}
    return None


def response_request_to_chat(request: ResponseCreateRequest) -> ChatCompletionRequest:
    if request.previous_response_id:
        raise ValueError("previous_response_id is not supported by the stateless router.")
    if request.conversation is not None:
        raise ValueError("Responses conversations are not supported by the stateless router.")
    if request.background:
        raise ValueError("Background Responses jobs are not supported.")
    if request.store is True:
        raise ValueError("store=true is not supported by the stateless router.")

    messages: list[ChatMessage] = []
    if request.instructions:
        messages.append(ChatMessage(role="system", content=request.instructions))

    if isinstance(request.input, str):
        messages.append(ChatMessage(role="user", content=request.input))
    elif isinstance(request.input, list):
        for item in request.input:
            if not isinstance(item, dict):
                messages.append(ChatMessage(role="user", content=str(item)))
                continue

            kind = item.get("type")
            if kind in {None, "message", "easy_input_message"} or item.get("role"):
                role = str(item.get("role") or "user")
                messages.append(
                    ChatMessage(
                        role=role,
                        content=_response_content_to_chat(item.get("content", "")),
                    )
                )
            elif kind == "function_call":
                call_id = str(item.get("call_id") or item.get("id") or "")
                if not call_id or not item.get("name"):
                    raise ValueError(
                        "Responses function_call requires call_id/id and name."
                    )
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content="",
                        tool_calls=[
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": item.get("name"),
                                    "arguments": item.get("arguments") or "{}",
                                },
                            }
                        ],
                    )
                )
            elif kind == "function_call_output":
                call_id = str(item.get("call_id") or item.get("id") or "")
                if not call_id:
                    raise ValueError(
                        "Responses function_call_output requires call_id/id."
                    )
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call_id,
                        content=item.get("output", ""),
                    )
                )
            else:
                raise ValueError(
                    f"Responses input item type {kind!r} is not supported."
                )
    else:
        messages.append(ChatMessage(role="user", content=request.input))

    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        stream=request.stream,
        temperature=request.temperature,
        top_p=request.top_p,
        max_completion_tokens=request.max_output_tokens,
        tools=_response_tools_to_chat(request.tools),
        tool_choice=_response_tool_choice_to_chat(request.tool_choice),
        response_format=_response_format_to_chat(request.text),
        user=request.user,
        metadata=request.metadata,
    )


def chat_body_to_response(
    body: dict[str, Any],
    request: ResponseCreateRequest,
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    choice = (body.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text_value = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    elif content is None:
        text_value = ""
    else:
        text_value = str(content)

    response_id = f"resp_router_{uuid.uuid4().hex[:20]}"
    message_id = f"msg_{uuid.uuid4().hex[:20]}"
    output: list[dict[str, Any]] = []
    if text_value or not message.get("tool_calls"):
        output.append(
            {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": text_value,
                        "annotations": [],
                    }
                ],
            }
        )

    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        output.append(
            {
                "id": tool_call.get("id") or f"fc_{uuid.uuid4().hex[:20]}",
                "type": "function_call",
                "call_id": tool_call.get("id") or f"call_{uuid.uuid4().hex[:20]}",
                "name": function.get("name"),
                "arguments": function.get("arguments") or "{}",
                "status": "completed",
            }
        )

    usage = body.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )
    total = int(usage.get("total_tokens") or prompt + completion)
    created = int(time.time())

    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "completed_at": created,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": request.instructions,
        "model": model,
        "output": output,
        "output_text": text_value,
        "parallel_tool_calls": (
            True if request.parallel_tool_calls is None else request.parallel_tool_calls
        ),
        "previous_response_id": None,
        "store": False,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_output_tokens": request.max_output_tokens,
        "text": request.text or {"format": {"type": "text"}},
        "tool_choice": request.tool_choice or "auto",
        "tools": request.tools or [],
        "usage": {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": total,
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        "router": {
            **(body.get("router") or {}),
            "provider": provider,
            "model": model,
        },
    }


def _event(payload: dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(payload, separators=(",", ":")) + "\n\n").encode()


async def chat_stream_to_responses(
    upstream: AsyncIterator[bytes],
    request: ResponseCreateRequest,
    *,
    provider: str,
    model: str,
) -> AsyncIterator[bytes]:
    response_id = f"resp_router_{uuid.uuid4().hex[:20]}"
    message_id = f"msg_{uuid.uuid4().hex[:20]}"
    created = int(time.time())
    sequence = 1
    text_value = ""

    base = {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": "in_progress",
        "model": model,
        "output": [],
        "error": None,
        "incomplete_details": None,
        "instructions": request.instructions,
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "store": False,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "tools": request.tools or [],
        "tool_choice": request.tool_choice or "auto",
        "usage": None,
        "router": {"provider": provider, "model": model},
    }
    yield _event({"type": "response.created", "response": base, "sequence_number": sequence})
    sequence += 1
    yield _event({"type": "response.in_progress", "response": base, "sequence_number": sequence})
    sequence += 1

    item = {
        "id": message_id,
        "status": "in_progress",
        "type": "message",
        "role": "assistant",
        "content": [],
    }
    yield _event(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": item,
            "sequence_number": sequence,
        }
    )
    sequence += 1
    yield _event(
        {
            "type": "response.content_part.added",
            "item_id": message_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
            "sequence_number": sequence,
        }
    )
    sequence += 1

    buffer = ""
    async for raw_chunk in upstream:
        buffer += raw_chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            event, buffer = buffer.split("\n\n", 1)
            for line in event.splitlines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                delta = ((payload.get("choices") or [{}])[0].get("delta") or {})
                part = delta.get("content")
                if not isinstance(part, str) or not part:
                    continue
                text_value += part
                yield _event(
                    {
                        "type": "response.output_text.delta",
                        "item_id": message_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": part,
                        "sequence_number": sequence,
                    }
                )
                sequence += 1

    yield _event(
        {
            "type": "response.output_text.done",
            "item_id": message_id,
            "output_index": 0,
            "content_index": 0,
            "text": text_value,
            "sequence_number": sequence,
        }
    )
    sequence += 1
    done_item = {
        "id": message_id,
        "status": "completed",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "output_text",
                "text": text_value,
                "annotations": [],
            }
        ],
    }
    yield _event(
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": done_item,
            "sequence_number": sequence,
        }
    )
    sequence += 1
    completed = {
        **base,
        "status": "completed",
        "completed_at": int(time.time()),
        "output": [done_item],
        "output_text": text_value,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }
    yield _event(
        {
            "type": "response.completed",
            "response": completed,
            "sequence_number": sequence,
        }
    )
