from app.quota_telemetry import parse_openrouter_key


def test_openrouter_key_telemetry_is_credit_scoped():
    parsed = parse_openrouter_key(
        {
            "data": {
                "usage": 1.25,
                "usage_daily": 0.2,
                "usage_monthly": 4.5,
                "limit": 10,
                "limit_remaining": 8.75,
                "limit_reset": "monthly",
                "is_free_tier": False,
            }
        }
    )
    assert parsed["credit_limit"] == 10
    assert parsed["credit_limit_remaining"] == 8.75
    assert parsed["credit_usage_daily"] == 0.2
    assert "requests_remaining" not in parsed
    assert parsed["source"] == "openrouter:/api/v1/key"


def test_openrouter_key_telemetry_handles_missing_limit():
    parsed = parse_openrouter_key({"data": {"usage_daily": 0, "is_free_tier": True}})
    assert parsed["credit_usage_daily"] == 0
    assert parsed["is_free_tier"] is True
    assert "credit_limit" not in parsed
