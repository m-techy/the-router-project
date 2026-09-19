import pytest

import app.main as main
from app.quota import QuotaManager
from app.registry import ProviderRegistry
from app.state import StateStore
from app.stream_usage import OpenAIStreamUsageMeter, StreamUsage


def test_stream_meter_uses_reported_provider_usage_when_present():
    meter = OpenAIStreamUsageMeter(prompt_tokens_estimate=99)
    meter.feed(
        b'data: {"choices":[{"delta":{"content":"hello"}}],'
        b'"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n'
    )
    meter.flush()

    usage = meter.usage()
    assert usage == StreamUsage(
        prompt_tokens=7,
        completion_tokens=3,
        total_tokens=10,
    )


def test_stream_meter_estimates_text_and_tool_deltas_without_usage():
    meter = OpenAIStreamUsageMeter(prompt_tokens_estimate=5)
    meter.feed(b'data: {"choices":[{"delta":{"content":"hello world"}}]}\n\n')
    meter.feed(
        b'data: {"choices":[{"delta":{"tool_calls":[{"function":'
        b'{"name":"lookup","arguments":"{\\\"q\\\":\\\"x\\\"}"}}]}}]}\n\n'
    )
    meter.feed(b"data: [DONE]\n\n")
    meter.flush()

    usage = meter.usage()
    assert usage.prompt_tokens == 5
    assert usage.completion_tokens > 0
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens


def test_failed_provider_attempt_counts_request_and_partial_tokens(tmp_path):
    registry = ProviderRegistry("config/providers.yaml")
    provider = registry.get("groq")
    store = StateStore(tmp_path / "quota.db")
    quota = QuotaManager(store)

    quota.record_failure(
        provider.id,
        model_id="model-x",
        request_id="stream-failed",
        status_code=500,
        prompt_tokens=4,
        completion_tokens=2,
        total_tokens=6,
        error="stream broke",
    )

    snapshot = quota.snapshot(provider)
    trace = store.request_trace("stream-failed")
    assert snapshot["day_requests"] == 1
    assert snapshot["day_tokens"] == 6
    assert trace[0]["success"] == 0
    assert trace[0]["total_tokens"] == 6
    store.close()


@pytest.mark.asyncio
async def test_project_stream_accounting_records_meter_total(monkeypatch):
    calls = []

    class FakeStore:
        def record_project_usage(self, project_id, *, requests=1, tokens=0):
            calls.append(
                {
                    "project_id": project_id,
                    "requests": requests,
                    "tokens": tokens,
                }
            )

    class FakeMeter:
        def usage(self):
            return StreamUsage(4, 6, 10)

    async def upstream():
        yield b"one"
        yield b"two"

    monkeypatch.setattr(main, "store", FakeStore())
    chunks = [
        chunk
        async for chunk in main.account_project_stream(
            upstream(),
            {"id": "project-1"},
            FakeMeter(),
        )
    ]

    assert chunks == [b"one", b"two"]
    assert calls == [
        {
            "project_id": "project-1",
            "requests": 0,
            "tokens": 10,
        }
    ]
