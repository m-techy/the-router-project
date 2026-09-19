from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable

import httpx

from app.models import ChatCompletionRequest, ProviderSpec
from app.providers.base import ProviderAdapter, ProviderError
from app.providers.openai_compatible import OpenAICompatibleAdapter

_NATIVE_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_COMPATIBILITY_FALLBACK_STATUSES = {400, 404, 405, 415, 422, 501}


def _text_part(text: str) -> dict[str, Any]:
    return {"text": text}


def _content_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [_text_part(content)]

    if not isinstance(content, list):
        return [_text_part(str(content))]

    parts: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(_text_part(str(item)))
            continue

        kind = item.get("type")
        if kind in {"text", "input_text"}:
            parts.append(_text_part(str(item.get("text", ""))))
            continue

        if kind == "image_url":
            raw = item.get("image_url")
            url = raw.get("url") if isinstance(raw, dict) else raw
            if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                header, data = url.split(",", 1)
                mime = header[5:].split(";", 1)[0] or "image/jpeg"
                parts.append({"inlineData": {"mimeType": mime, "data": data}})
                continue
            raise ProviderError(
                "Gemini native fallback supports inline data: image URLs only; "
                "remote image URLs should use Gemini OpenAI compatibility.",
                422,
            )

        parts.append(_text_part(json.dumps(item, ensure_ascii=False)))
    return parts


def _tool_declarations(tools: Any) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return declarations

    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function") or {}
        if not isinstance(function, dict) or not function.get("name"):
            continue
        declaration: dict[str, Any] = {
            "name": function["name"],
        }
        if function.get("description"):
            declaration["description"] = function["description"]
        if function.get("parameters"):
            declaration["parameters"] = function["parameters"]
        declarations.append(declaration)
    return declarations


def _tool_config(tool_choice: Any) -> dict[str, Any] | None:
    if tool_choice is None or tool_choice == "auto":
        return None
    if tool_choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if tool_choice == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if isinstance(tool_choice, dict):
        function = tool_choice.get("function") or {}
        name = function.get("name") if isinstance(function, dict) else None
        if name:
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [name],
                }
            }
    return None


def build_native_payload(request: ChatCompletionRequest) -> dict[str, Any]:
    contents: list[dict[str, Any]] = []
    system_parts: list[dict[str, Any]] = []
    tool_call_names: dict[str, str] = {}

    for history_message in request.messages:
        if not history_message.tool_calls or not isinstance(history_message.tool_calls, list):
            continue
        for call in history_message.tool_calls:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            function = call.get("function") or {}
            name = function.get("name") if isinstance(function, dict) else None
            if call_id and name:
                tool_call_names[str(call_id)] = str(name)

    for message in request.messages:
        if message.role in {"system", "developer"}:
            system_parts.extend(_content_parts(message.content))
            continue

        if message.role == "tool":
            name = message.name or tool_call_names.get(message.tool_call_id or "") or "tool"
            response: Any
            if isinstance(message.content, str):
                try:
                    response = json.loads(message.content)
                except json.JSONDecodeError:
                    response = {"result": message.content}
            else:
                response = message.content
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name,
                                "response": response
                                if isinstance(response, dict)
                                else {"result": response},
                            }
                        }
                    ],
                }
            )
            continue

        role = "model" if message.role == "assistant" else "user"
        parts = _content_parts(message.content)

        if message.tool_calls and isinstance(message.tool_calls, list):
            for call in message.tool_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                name = function.get("name")
                if not name:
                    continue
                raw_arguments = function.get("arguments") or "{}"
                try:
                    arguments = (
                        raw_arguments
                        if isinstance(raw_arguments, dict)
                        else json.loads(raw_arguments)
                    )
                except (json.JSONDecodeError, TypeError):
                    arguments = {"_raw": raw_arguments}
                parts.append(
                    {
                        "functionCall": {
                            "name": name,
                            "args": arguments,
                        }
                    }
                )

        contents.append({"role": role, "parts": parts})

    payload: dict[str, Any] = {"contents": contents}

    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}

    declarations = _tool_declarations(request.tools)
    if declarations:
        payload["tools"] = [{"functionDeclarations": declarations}]

    tool_config = _tool_config(request.tool_choice)
    if tool_config:
        payload["toolConfig"] = tool_config

    generation: dict[str, Any] = {}
    if request.temperature is not None:
        generation["temperature"] = request.temperature
    if request.top_p is not None:
        generation["topP"] = request.top_p
    max_tokens = request.max_completion_tokens or request.max_tokens
    if max_tokens is not None:
        generation["maxOutputTokens"] = max_tokens
    if request.stop is not None:
        generation["stopSequences"] = (
            request.stop if isinstance(request.stop, list) else [request.stop]
        )

    if request.response_format:
        response_type = (
            request.response_format.get("type")
            if isinstance(request.response_format, dict)
            else None
        )
        if response_type in {"json_object", "json_schema"}:
            generation["responseMimeType"] = "application/json"
            if response_type == "json_schema":
                schema = request.response_format.get("json_schema") or {}
                if isinstance(schema, dict):
                    native_schema = schema.get("schema")
                    if native_schema:
                        generation["responseJsonSchema"] = native_schema

    if generation:
        payload["generationConfig"] = generation

    return payload


def _finish_reason(reason: str | None) -> str:
    mapping = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "MALFORMED_FUNCTION_CALL": "tool_calls",
    }
    return mapping.get(reason or "", "stop")


def native_response_to_openai(
    payload: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    candidate = candidates[0] if candidates else {}
    content = candidate.get("content") or {}
    parts = content.get("parts") or []

    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        if "text" in part and not part.get("thought"):
            text_chunks.append(str(part.get("text", "")))
        function_call = part.get("functionCall")
        if isinstance(function_call, dict):
            tool_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {
                        "name": function_call.get("name", f"tool_{index}"),
                        "arguments": json.dumps(
                            function_call.get("args") or {},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
            )

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_chunks) or None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    usage = payload.get("usageMetadata") or {}
    prompt_tokens = int(usage.get("promptTokenCount") or 0)
    completion_tokens = int(usage.get("candidatesTokenCount") or 0)
    total_tokens = int(
        usage.get("totalTokenCount") or (prompt_tokens + completion_tokens)
    )

    return {
        "id": f"chatcmpl-gemini-{uuid.uuid4().hex[:20]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _finish_reason(candidate.get("finishReason")),
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


def native_chunk_to_openai(
    payload: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any] | None:
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    candidate = candidates[0]
    content = candidate.get("content") or {}
    parts = content.get("parts") or []

    delta: dict[str, Any] = {}
    text_chunks = [
        str(part.get("text", ""))
        for part in parts
        if isinstance(part, dict) and "text" in part and not part.get("thought")
    ]
    if text_chunks:
        delta["content"] = "".join(text_chunks)

    tool_calls: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        function_call = part.get("functionCall")
        if isinstance(function_call, dict):
            tool_calls.append(
                {
                    "index": index,
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {
                        "name": function_call.get("name", f"tool_{index}"),
                        "arguments": json.dumps(
                            function_call.get("args") or {},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
            )
    if tool_calls:
        delta["tool_calls"] = tool_calls

    finish_reason = (
        _finish_reason(candidate.get("finishReason"))
        if candidate.get("finishReason")
        else None
    )
    if not delta and finish_reason is None:
        return None

    return {
        "id": f"chatcmpl-gemini-{uuid.uuid4().hex[:20]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


class GeminiNativeAdapter(ProviderAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        value_resolver: Callable[[str], str | None] | None = None,
    ):
        self.client = client
        self._value_resolver = value_resolver or (lambda _: None)

    def _api_key(self, provider: ProviderSpec) -> str | None:
        if not provider.env_key:
            return None
        return os.getenv(provider.env_key) or self._value_resolver(provider.env_key)

    def _headers(self, provider: ProviderSpec) -> dict[str, str]:
        key = self._api_key(provider)
        if not key:
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        }

    def _url(self, model: str, *, stream: bool) -> str:
        method = "streamGenerateContent" if stream else "generateContent"
        suffix = "?alt=sse" if stream else ""
        return f"{_NATIVE_ROOT}/models/{model}:{method}{suffix}"

    async def chat(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ):
        try:
            response = await self.client.post(
                self._url(model, stream=False),
                headers=self._headers(provider),
                json=build_native_payload(request),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Gemini native API returned a non-JSON response",
                response.status_code,
            ) from exc

        return native_response_to_openai(payload, model=model), response.headers

    async def stream(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[bytes]:
        try:
            async with self.client.stream(
                "POST",
                self._url(model, stream=True),
                headers=self._headers(provider),
                json=build_native_payload(request),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ProviderError(
                        body.decode(errors="replace")[:1000],
                        response.status_code,
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    chunk = native_chunk_to_openai(payload, model=model)
                    if chunk is not None:
                        yield (
                            "data: "
                            + json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
                            + "\n\n"
                        ).encode()

                yield b"data: [DONE]\n\n"
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc


class GeminiHybridAdapter(ProviderAdapter):
    """Prefer Gemini's OpenAI facade, then use native REST for compatibility gaps."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        value_resolver: Callable[[str], str | None] | None = None,
    ):
        self.openai = OpenAICompatibleAdapter(client, value_resolver)
        self.native = GeminiNativeAdapter(client, value_resolver)

    @staticmethod
    def _should_fallback(exc: ProviderError) -> bool:
        return exc.status_code in _COMPATIBILITY_FALLBACK_STATUSES

    async def chat(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ):
        try:
            return await self.openai.chat(provider, model, request)
        except ProviderError as exc:
            if not self._should_fallback(exc):
                raise
            return await self.native.chat(provider, model, request)

    async def stream(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[bytes]:
        yielded = False
        try:
            async for chunk in self.openai.stream(provider, model, request):
                yielded = True
                yield chunk
            return
        except ProviderError as exc:
            if yielded or not self._should_fallback(exc):
                raise

        async for chunk in self.native.stream(provider, model, request):
            yield chunk
