from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical_promotion import canonical_part, evaluate, listing_identity, records_from_output


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


def _canonical_id(record: Mapping[str, Any]) -> str:
    try:
        return str(canonical_part(record).get("id", ""))
    except (TypeError, ValueError):
        return ""


def _canonical_provenance(catalog: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for item in catalog.get("parts", []) if isinstance(catalog.get("parts"), list) else []:
        if not isinstance(item, Mapping):
            continue
        provenance = item.get("promotion_provenance")
        if not isinstance(provenance, Mapping):
            continue
        identity = listing_identity({
            "source": provenance.get("source"),
            "source_id": provenance.get("source_id"),
            "listing_url": provenance.get("listing_url") or item.get("url"),
        })
        if identity[0] and identity[1]:
            result[identity] = str(item.get("id") or "")
    return result


def project_promotion_records(
    records: Sequence[Mapping[str, Any]],
    *,
    report: Mapping[str, Any] | None = None,
    catalog: Mapping[str, Any] | None = None,
    min_source_confidence: float = 0.80,
    min_sku_confidence: float = 0.55,
) -> dict[str, Any]:
    """Project current records into promotion state using persisted last decisions."""
    report = report or {}
    catalog = catalog or {}
    canonical = _canonical_provenance(catalog)
    decision_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in report.get("decisions", []) if isinstance(report.get("decisions"), list) else []:
        if isinstance(item, Mapping):
            decision_index[listing_identity(item)] = dict(item)
    held_index: dict[tuple[str, str], list[str]] = {}
    for item in report.get("held", []) if isinstance(report.get("held"), list) else []:
        if isinstance(item, Mapping):
            held_index[listing_identity(item)] = [str(reason) for reason in item.get("reasons", [])]

    report_generated_at = _parse_time(report.get("generated_at"))
    items: list[dict[str, Any]] = []
    counts = {state: 0 for state in STATES}
    reason_counts: dict[str, int] = {}

    for record in records:
        row = dict(record)
        identity = listing_identity(record)
        observed_at = _parse_time(record.get("observed_at") or record.get("last_seen_at"))
        reasons: list[str] = []
        canonical_id = canonical.get(identity)
        persisted = decision_index.get(identity)

        if canonical_id:
            state = "canonical"
        elif report_generated_at is None or (observed_at is not None and observed_at > report_generated_at):
            state = "discovered"
        elif persisted is not None:
            state = str(persisted.get("state") or "discovered")
            reasons = [str(value) for value in persisted.get("reasons", [])]
            canonical_id = str(persisted.get("canonical_id") or "") or None
        elif identity in held_index:
            state = "held"
            reasons = held_index[identity]
        else:
            reasons = evaluate(record, min_source_confidence=min_source_confidence, min_sku_confidence=min_sku_confidence)
            state = "held" if reasons else "promotion_ready"

        counts[state] = counts.get(state, 0) + 1
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        row["source"], row["source_id"] = identity
        row["promotion_state"] = state
        row["promotion_reasons"] = reasons
        row["canonical_id"] = canonical_id or (_canonical_id(record) if state == "promotion_ready" else None)
        items.append(row)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "promotion_report_generated_at": report.get("generated_at"),
        "counts": counts,
        "reason_counts": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "total": len(items),
        "items": items,
    }


def build_promotion_snapshot(
    *,
    discovery_path: str | Path = "results/discovery-latest.json",
    report_path: str | Path = "results/promotion-latest.json",
    catalog_path: str | Path = "data/catalog/auto-promoted.json",
    min_source_confidence: float = 0.80,
    min_sku_confidence: float = 0.55,
) -> dict[str, Any]:
    discovery = Path(discovery_path)
    report_file = Path(report_path)
    catalog_file = Path(catalog_path)
    snapshot = project_promotion_records(
        records_from_output(discovery),
        report=_load_json(report_file),
        catalog=_load_json(catalog_file),
        min_source_confidence=min_source_confidence,
        min_sku_confidence=min_sku_confidence,
    )
    snapshot["paths"] = {"discovery": str(discovery), "report": str(report_file), "catalog": str(catalog_file)}
    return snapshot


def filter_promotion_items(items: Sequence[Mapping[str, Any]], *, state: str = "", reason: str = "", query: str = "", source: str = "") -> list[dict[str, Any]]:
    state = state.strip().lower(); reason = reason.strip(); query = query.strip().lower(); source = source.strip().lower()
    result: list[dict[str, Any]] = []
    for value in items:
        if state and str(value.get("promotion_state", "")).lower() != state: continue
        reasons = [str(item) for item in value.get("promotion_reasons", [])]
        if reason and reason not in reasons: continue
        if source and str(value.get("source", "")).lower() != source: continue
        if query:
            haystack = " ".join(str(value.get(key, "")) for key in ("title", "source", "source_id", "listing_url", "manufacturer", "sku", "mpn")).lower()
            if query not in haystack: continue
        result.append(dict(value))
    return result
