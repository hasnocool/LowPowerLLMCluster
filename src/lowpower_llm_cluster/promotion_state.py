from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical_promotion import canonical_part, evaluate, records_from_output


STATES = ("discovered", "held", "promotion_ready", "canonical")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _identity(record: Mapping[str, Any]) -> tuple[str, str]:
    return str(record.get("source", "")), str(record.get("source_id", ""))


def _canonical_id(record: Mapping[str, Any]) -> str:
    try:
        return str(canonical_part(record).get("id", ""))
    except (TypeError, ValueError):
        return ""


def build_promotion_snapshot(
    *,
    discovery_path: str | Path = "results/discovery-latest.json",
    report_path: str | Path = "results/promotion-latest.json",
    catalog_path: str | Path = "data/catalog/auto-promoted.json",
    min_source_confidence: float = 0.80,
    min_sku_confidence: float = 0.55,
) -> dict[str, Any]:
    """Project live discovery records into the promotion workflow.

    State precedence is canonical -> newly discovered since the latest promotion report ->
    persisted held decision -> freshly evaluated held/promotion-ready. This keeps the UI
    useful even when the scanner has produced records newer than the last promotion pass.
    """
    discovery = Path(discovery_path)
    report_file = Path(report_path)
    catalog_file = Path(catalog_path)
    records = records_from_output(discovery)
    report = _load_json(report_file)
    catalog = _load_json(catalog_file)

    canonical_ids = {
        str(item.get("id"))
        for item in catalog.get("parts", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    held_index: dict[tuple[str, str], list[str]] = {}
    for item in report.get("held", []):
        if not isinstance(item, Mapping):
            continue
        held_index[_identity(item)] = [str(reason) for reason in item.get("reasons", [])]

    report_generated_at = _parse_time(report.get("generated_at"))
    items: list[dict[str, Any]] = []
    counts = {state: 0 for state in STATES}
    reason_counts: dict[str, int] = {}

    for record in records:
        row = dict(record)
        pid = _canonical_id(record)
        observed_at = _parse_time(record.get("observed_at"))
        reasons: list[str] = []

        if pid and pid in canonical_ids:
            state = "canonical"
        elif report_generated_at is None or (observed_at is not None and observed_at > report_generated_at):
            state = "discovered"
        elif _identity(record) in held_index:
            state = "held"
            reasons = held_index[_identity(record)]
        else:
            reasons = evaluate(
                record,
                min_source_confidence=min_source_confidence,
                min_sku_confidence=min_sku_confidence,
            )
            state = "held" if reasons else "promotion_ready"

        counts[state] += 1
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        row["promotion_state"] = state
        row["promotion_reasons"] = reasons
        row["canonical_id"] = pid or None
        items.append(row)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "promotion_report_generated_at": report.get("generated_at"),
        "paths": {
            "discovery": str(discovery),
            "report": str(report_file),
            "catalog": str(catalog_file),
        },
        "counts": counts,
        "reason_counts": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "total": len(items),
        "items": items,
    }


def filter_promotion_items(
    items: Sequence[Mapping[str, Any]],
    *,
    state: str = "",
    reason: str = "",
    query: str = "",
    source: str = "",
) -> list[dict[str, Any]]:
    state = state.strip().lower()
    reason = reason.strip()
    query = query.strip().lower()
    source = source.strip()
    result: list[dict[str, Any]] = []
    for value in items:
        if state and str(value.get("promotion_state", "")).lower() != state:
            continue
        reasons = [str(item) for item in value.get("promotion_reasons", [])]
        if reason and reason not in reasons:
            continue
        if source and str(value.get("source", "")) != source:
            continue
        if query:
            haystack = " ".join(
                str(value.get(key, ""))
                for key in ("title", "source", "source_id", "listing_url", "manufacturer", "sku", "mpn")
            ).lower()
            if query not in haystack:
                continue
        result.append(dict(value))
    return result
