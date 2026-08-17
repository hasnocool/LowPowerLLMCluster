from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .catalog import project_root
from .market import load_fx


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else project_root() / "data" / "market" / "secondary-accelerator-policy.json"
    if not target.exists():
        return {"schema_version": 1, "tax_rate": 0.12, "watches": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _text(record: Mapping[str, Any]) -> str:
    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    values = (
        record.get("title"),
        record.get("manufacturer"),
        record.get("sku"),
        record.get("mpn"),
        attrs.get("accelerator"),
        attrs.get("hardware_class"),
    )
    return " ".join(str(value or "") for value in values).casefold()


def match_watch(record: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    policy = policy or load_policy()
    text = _text(record)
    for watch in policy.get("watches", []):
        if not isinstance(watch, Mapping):
            continue
        keywords = [str(value).casefold() for value in watch.get("keywords", [])]
        excludes = [str(value).casefold() for value in watch.get("exclude_keywords", [])]
        if keywords and not any(keyword in text for keyword in keywords):
            continue
        if excludes and any(keyword in text for keyword in excludes):
            continue
        return dict(watch)
    return None


def landed_cad(record: Mapping[str, Any], *, policy: Mapping[str, Any] | None = None) -> float | None:
    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    for value in (
        record.get("landed_cost_cad"),
        record.get("landed_cad"),
        attrs.get("landed_cost_cad"),
        attrs.get("landed_cad"),
    ):
        if isinstance(value, (int, float)) and float(value) >= 0:
            return round(float(value), 2)

    price = record.get("price")
    if not isinstance(price, (int, float)):
        return None
    currency = str(record.get("currency") or "").upper()
    shipping_currency = str(record.get("shipping_currency") or currency).upper()
    try:
        fx = load_fx()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if currency not in fx or shipping_currency not in fx:
        return None
    shipping = record.get("shipping")
    shipping_value = float(shipping) if isinstance(shipping, (int, float)) else 0.0
    policy = policy or load_policy()
    tax_rate = float(policy.get("tax_rate", 0.12))
    item_cad = float(price) * float(fx[currency])
    shipping_cad = shipping_value * float(fx[shipping_currency])
    return round((item_cad + shipping_cad) * (1.0 + tax_rate), 2)


def runtime_evidence(record: Mapping[str, Any]) -> tuple[bool, str | None]:
    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    explicit = attrs.get("transformer_runtime_verified")
    runtime = str(
        attrs.get("demonstrated_transformer_runtime")
        or attrs.get("transformer_runtime")
        or attrs.get("llm_runtime")
        or ""
    ).strip()
    if explicit is True and runtime:
        return True, runtime
    return False, runtime or None


def evaluate_secondary_accelerator(
    record: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    policy = policy or load_policy()
    watch = match_watch(record, policy)
    if watch is None:
        return []

    reasons: list[str] = []
    landed = landed_cad(record, policy=policy)
    ceiling = watch.get("max_landed_cad")
    if landed is None:
        reasons.append("accelerator_landed_cost_missing")
    elif isinstance(ceiling, (int, float)) and landed > float(ceiling):
        reasons.append("accelerator_landed_cost_above_threshold")

    verified_runtime, runtime = runtime_evidence(record)
    if watch.get("transformer_runtime_required", True) and not verified_runtime:
        reasons.append("accelerator_transformer_runtime_unverified")
    if verified_runtime:
        aliases = [str(value).casefold() for value in watch.get("runtime_aliases", [])]
        if aliases and runtime and not any(alias in runtime.casefold() for alias in aliases):
            reasons.append("accelerator_runtime_not_in_approved_family")

    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    memory = attrs.get("memory_capacity_gb") or attrs.get("max_memory_gb")
    expected_memory = watch.get("memory_gb")
    if isinstance(memory, (int, float)) and isinstance(expected_memory, (int, float)):
        if float(memory) != float(expected_memory):
            reasons.append("accelerator_memory_identity_mismatch")

    return reasons


def promotion_snapshot(record: Mapping[str, Any], *, policy: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    policy = policy or load_policy()
    watch = match_watch(record, policy)
    if watch is None:
        return None
    verified_runtime, runtime = runtime_evidence(record)
    landed = landed_cad(record, policy=policy)
    ceiling = watch.get("max_landed_cad")
    return {
        "watch_id": watch.get("id"),
        "landed_cad": landed,
        "max_landed_cad": ceiling,
        "economic_eligible": landed is not None and isinstance(ceiling, (int, float)) and landed <= float(ceiling),
        "transformer_runtime_verified": verified_runtime,
        "transformer_runtime": runtime,
        "eligible": not evaluate_secondary_accelerator(record, policy=policy),
    }
