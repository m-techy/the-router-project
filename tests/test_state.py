import time
from app.state import StateStore
def test_usage_summary(tmp_path):
    store=StateStore(tmp_path/"router.db")
    store.record_usage(ts=time.time(),request_id="r1",provider_id="p1",model_id="m1",success=1,status_code=200,prompt_tokens=5,completion_tokens=7,total_tokens=12,latency_ms=100,fallback_count=0,error=None)
    summary=store.usage_summary(time.time()-10)
    assert summary["totals"]["requests"]==1
    assert summary["totals"]["tokens"]==12
    assert summary["by_provider"][0]["provider_id"]=="p1"
    store.close()
