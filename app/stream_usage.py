from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class StreamUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIStreamUsageMeter:
    def __init__(self, prompt_tokens_estimate: int):
        self.prompt_tokens_estimate = max(0, int(prompt_tokens_estimate))
        self._buffer = ""
        self._completion_chars = 0
        self._reported_prompt = 0
        self._reported_completion = 0
        self._reported_total = 0

    def feed(self, chunk: bytes) -> None:
        self._buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in self._buffer:
            event, self._buffer = self._buffer.split("\n\n", 1)
            self._consume_event(event)

    def flush(self) -> None:
        if self._buffer.strip():
            self._consume_event(self._buffer)
        self._buffer = ""

    def _consume_event(self, event: str) -> None:
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

            usage = payload.get("usage") or {}
            if isinstance(usage, dict):
                self._reported_prompt = max(
                    self._reported_prompt,
                    int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
                )
                self._reported_completion = max(
                    self._reported_completion,
                    int(
                        usage.get("completion_tokens")
                        or usage.get("output_tokens")
                        or 0
                    ),
                )
                self._reported_total = max(
                    self._reported_total,
                    int(usage.get("total_tokens") or 0),
                )

            for choice in payload.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    continue
                for field in ("content", "reasoning_content", "reasoning"):
                    value = delta.get(field)
                    if isinstance(value, str):
                        self._completion_chars += len(value)
                for tool_call in delta.get("tool_calls") or []:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    if not isinstance(function, dict):
                        continue
                    for field in ("name", "arguments"):
                        value = function.get(field)
                        if isinstance(value, str):
                            self._completion_chars += len(value)

    def usage(self) -> StreamUsage:
        if self._reported_total > 0:
            prompt = self._reported_prompt
            completion = self._reported_completion
            total = self._reported_total
            if not prompt and total >= completion:
                prompt = total - completion
            if not completion and total >= prompt:
                completion = total - prompt
            return StreamUsage(prompt, completion, total)

        prompt = self._reported_prompt or self.prompt_tokens_estimate
        completion = self._reported_completion or max(
            0,
            (self._completion_chars + 3) // 4,
        )
        total = prompt + completion
        return StreamUsage(prompt, completion, total)
