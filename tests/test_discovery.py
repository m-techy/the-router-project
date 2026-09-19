from app.discovery import classify_zero_price, model_entries


def test_zero_price_nested_pricing():
    zero, evidence = classify_zero_price(
        {"pricing": {"prompt": "0", "completion": 0, "request": "$0"}}
    )
    assert zero is True
    assert evidence["pricing.prompt"] == "0"


def test_positive_price_is_not_free():
    zero, evidence = classify_zero_price(
        {"input_price": "0", "output_price": "0.25"}
    )
    assert zero is False
    assert evidence["output_price"] == "0.25"


def test_unknown_pricing_stays_unknown():
    zero, evidence = classify_zero_price({"id": "model", "context_length": 128000})
    assert zero is None
    assert evidence == {}


def test_model_entries_preserve_unknown_vs_explicit_free():
    entries = model_entries(
        {
            "data": [
                {"id": "free-model", "pricing": {"input": 0, "output": 0}},
                {"id": "paid-model", "pricing": {"input": 0.1, "output": 0.2}},
                {"id": "unknown-model"},
            ]
        }
    )
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id["free-model"]["zero_price"] is True
    assert by_id["paid-model"]["zero_price"] is False
    assert by_id["unknown-model"]["zero_price"] is None
