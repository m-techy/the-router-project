import time

from app.state import StateStore


def test_usage_summary_and_trace(tmp_path):
    store = StateStore(tmp_path / "router.db")
    store.record_usage(
        ts=time.time(),
        request_id="r1",
        provider_id="p1",
        model_id="m1",
        success=0,
        status_code=429,
        prompt_tokens=5,
        completion_tokens=0,
        total_tokens=5,
        latency_ms=100,
        fallback_count=0,
        error="rate limited",
    )
    store.record_usage(
        ts=time.time(),
        request_id="r1",
        provider_id="p2",
        model_id="m2",
        success=1,
        status_code=200,
        prompt_tokens=5,
        completion_tokens=7,
        total_tokens=12,
        latency_ms=80,
        fallback_count=1,
        error=None,
    )

    summary = store.usage_summary(time.time() - 10)
    assert summary["totals"]["requests"] == 2
    assert summary["totals"]["tokens"] == 17
    assert {row["provider_id"] for row in summary["by_provider"]} == {"p1", "p2"}

    trace = store.request_trace("r1")
    assert [row["provider_id"] for row in trace] == ["p1", "p2"]
    assert trace[0]["success"] == 0
    assert trace[1]["fallback_count"] == 1

    store.set_setting("ui.theme", {"mode": "dark"})
    assert store.get_setting("ui.theme") == {"mode": "dark"}
    assert store.get_setting("missing", "fallback") == "fallback"
    store.close()
