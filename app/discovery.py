from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

PRICE_KEYS = {
    "input",
    "output",
    "prompt",
    "completion",
    "request",
    "input_price",
    "output_price",
    "prompt_price",
    "completion_price",
    "request_price",
    "input_cost",
    "output_cost",
    "prompt_cost",
    "completion_cost",
}


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"free", "n/a", "none", "null", "-"}:
            return Decimal("0") if text == "free" else None
        for token in ("$", "usd", "/1m", "per_million", "per million"):
            text = text.replace(token, "")
        text = text.strip()
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _pricing_pairs(item: dict[str, Any]) -> list[tuple[str, Decimal]]:
    pairs: list[tuple[str, Decimal]] = []

    def collect(mapping: Any, prefix: str = "") -> None:
        if not isinstance(mapping, dict):
            return
        for key, value in mapping.items():
            normalized = str(key).lower().replace("-", "_")
            full_key = f"{prefix}.{normalized}" if prefix else normalized
            if normalized in PRICE_KEYS:
                number = _number(value)
                if number is not None:
                    pairs.append((full_key, number))

    collect(item)
    for container in ("pricing", "price", "cost", "costs", "rates"):
        collect(item.get(container), container)
    return pairs


def classify_zero_price(item: dict[str, Any]) -> tuple[bool | None, dict[str, str]]:
    """Return (zero_price, evidence).

    True: explicit known price fields exist and every parsed price is zero.
    False: explicit known price fields exist and at least one is positive.
    None: no recognized numeric pricing metadata exists.
    """
    pairs = _pricing_pairs(item)
    if not pairs:
        return None, {}
    evidence = {key: str(value) for key, value in pairs}
    if any(value > 0 for _, value in pairs):
        return False, evidence
    return True, evidence


def model_id(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return None
    value = item.get("id") or item.get("name") or item.get("model")
    return str(value) if value else None


def model_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw = payload.get("data", payload.get("models", []))
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []

    entries: list[dict[str, Any]] = []
    for item in raw:
        identifier = model_id(item)
        if not identifier:
            continue
        if isinstance(item, dict):
            zero_price, evidence = classify_zero_price(item)
        else:
            zero_price, evidence = None, {}
        entries.append(
            {
                "id": identifier,
                "zero_price": zero_price,
                "pricing_evidence": evidence,
            }
        )
    return entries
