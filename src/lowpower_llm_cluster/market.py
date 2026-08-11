# src/lowpower_llm_cluster/market.py
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .catalog import project_root
from .identity_extraction import enrich_hardware_identity, extract_seller_firmware_evidence

CONFIDENCE = {"unknown": 0.0, "low": 0.25, "medium": 0.55, "high": 0.8, "exact": 1.0}
PERF_SOURCE = {"unknown": 0.0, "spec_based_estimate": 0.15, "derived_estimate": 0.35, "vendor_measured": 0.6, "community_measured": 0.8, "measured_local": 1.0}
MEASURED_SOURCES = {"vendor_measured", "community_measured", "measured_local"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().replace("-", " ").split())


def _tokens(value: str | None) -> set[str]:
    return {token for token in _norm(value).split() if len(token) > 1}


def watch_scope(queries: list[str]) -> str:
    normalized = "\n".join(sorted(_norm(query) for query in queries if query.strip())) or "__all__"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    price: float
    currency: str
    observed_at: str
    seller: str | None = None
    sku: str | None = None
    configuration: dict[str, Any] | None = None
    shipping: float | None = None
    shipping_currency: str | None = None
    destination_country: str | None = None
    availability: str | None = None
    source_kind: str = "unknown"
    seller_metrics: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        enriched = enrich_hardware_identity(self.title, existing=dict(self.configuration or {}))
        if self.source_kind == "structured_marketplace":
            seller_fw = extract_seller_firmware_evidence(self.title)
            if seller_fw.get("board_revision") or seller_fw.get("installed_bios_version"):
                enriched.setdefault("seller_firmware_evidence", seller_fw)
                if seller_fw.get("board_revision"):
                    enriched.setdefault("board_revision", seller_fw["board_revision"])
                if seller_fw.get("installed_bios_version"):
                    enriched.setdefault("installed_bios_version", seller_fw["installed_bios_version"])
        object.__setattr__(self, "configuration", enriched)

    @classmethod
    def from_mapping(cls, item: dict[str, Any], source: str) -> "Listing":
        return cls(
            source=source,
            source_id=str(item.get("source_id") or item.get("id") or item.get("url")),
            url=str(item["url"]), title=str(item["title"]), price=float(item["price"]),
            currency=str(item.get("currency", "USD")).upper(), observed_at=str(item.get("observed_at") or _now()),
            seller=item.get("seller"), sku=item.get("sku"), configuration=item.get("configuration") or {},
            shipping=float(item["shipping"]) if item.get("shipping") is not None else None,
            shipping_currency=str(item.get("shipping_currency") or item.get("currency", "USD")).upper(),
            destination_country=item.get("destination_country"), availability=item.get("availability"),
            source_kind=str(item.get("source_kind") or "unknown"), seller_metrics=item.get("seller_metrics") or {},
        )


class DiscoveryAdapter:
    """Interface for product discovery sources. Implementations must use non-blocking I/O."""
    name = "base"
    enabled = True

    async def discover(self, queries: list[str]) -> list[Listing]:
        raise NotImplementedError


class JsonFeedAdapter(DiscoveryAdapter):
    """Deterministic adapter for API/export fixtures; file I/O is moved off the event loop."""

    def __init__(self, path: Path, name: str = "json-feed") -> None:
        self.path = path
        self.name = name

    async def discover(self, queries: list[str]) -> list[Listing]:
        payload = await asyncio.to_thread(_read_json, self.path, {"listings": []})
        needles = [_tokens(query) for query in queries]
        listings = [Listing.from_mapping(item, self.name) for item in payload.get("listings", [])]
        if not needles:
            return listings
        return [item for item in listings if any(needle <= _tokens(item.title) for needle in needles)]


def source_confidence(listing: Listing) -> dict[str, Any]:
    metrics = listing.seller_metrics or {}
    kind = listing.source_kind
    if kind in {"manufacturer", "authorized_distributor"} and metrics.get("verified_source"):
        return {"score": 0.95, "label": "high", "basis": "verified_source"}
    score = 0.35
    feedback = metrics.get("feedback_percentage")
    count = metrics.get("feedback_score")
    if feedback is not None:
        score += max(0.0, min(0.30, (float(feedback) - 95.0) * 0.06))
    if count is not None:
        score += min(0.20, math.log10(max(1.0, float(count))) * 0.04)
    if metrics.get("top_rated"):
        score += 0.10
    score = min(score, 0.85 if kind == "structured_marketplace" else 0.75)
    label = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return {"score": round(score, 3), "label": label, "basis": "seller_source_metrics"}


def configuration_confidence(part: dict[str, Any], listing: Listing) -> dict[str, Any]:
    expected_sku = _norm(str(part.get("sku") or part.get("model") or ""))
    observed_sku = _norm(listing.sku)
    if expected_sku and observed_sku and expected_sku == observed_sku:
        sku_score = 1.0
    elif expected_sku and expected_sku in _norm(listing.title):
        sku_score = 0.8
    else:
        overlap = _tokens(part.get("name")) & _tokens(listing.title)
        sku_score = min(0.65, len(overlap) / max(1, len(_tokens(part.get("name")))))
    config = listing.configuration or {}
    checks: list[float] = []
    for key in ("memory_capacity_gb", "storage_gb", "cpu", "soc"):
        expected = part.get(key)
        observed = config.get(key)
        if expected is not None and observed is not None:
            checks.append(1.0 if _norm(str(expected)) == _norm(str(observed)) else 0.0)
    config_score = sum(checks) / len(checks) if checks else 0.5
    score = round((sku_score * 0.65) + (config_score * 0.35), 3)
    label = "exact" if score >= 0.9 else "high" if score >= 0.72 else "medium" if score >= 0.5 else "low"
    return {"score": score, "label": label, "sku_score": round(sku_score, 3), "configuration_score": round(config_score, 3)}


def match_listing(parts: list[dict[str, Any]], listing: Listing) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    ranked = sorted(((configuration_confidence(part, listing), part) for part in parts), key=lambda row: row[0]["score"], reverse=True)
    if not ranked or ranked[0][0]["score"] < 0.35:
        return None, {"score": 0.0, "label": "unknown"}
    confidence, part = ranked[0]
    return part, confidence


async def discover_all(adapters: Iterable[DiscoveryAdapter], queries: list[str]) -> list[Listing]:
    groups = await asyncio.gather(*(adapter.discover(queries) for adapter in adapters if getattr(adapter, "enabled", True)))
    deduped: dict[tuple[str, str], Listing] = {}
    for group in groups:
        for item in group:
            deduped[(item.source, item.source_id)] = item
    return list(deduped.values())


def append_price_observations(listings: list[Listing], parts: list[dict[str, Any]], path: Path | None = None, *, scope: str | None = None) -> dict[str, int]:
    target = path or project_root() / "data" / "market" / "price-history.json"
    history = _read_json(target, {"schema_version": 1, "observations": []})
    observations = history.setdefault("observations", [])
    existing = {(row["source"], row["source_id"], row["observed_at"], row["price"], row["currency"]) for row in observations}
    added = 0
    for listing in listings:
        part, confidence = match_listing(parts, listing)
        row = {**asdict(listing), "part_id": part.get("id") if part else None, "configuration_confidence": confidence, "seller_confidence": source_confidence(listing), "watch_scope": scope}
        key = (row["source"], row["source_id"], row["observed_at"], row["price"], row["currency"])
        if key not in existing:
            observations.append(row); existing.add(key); added += 1
    observations.sort(key=lambda row: row["observed_at"])
    _write_json(target, history)
    return {"added": added, "total": len(observations)}


def price_history(part_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "market" / "price-history.json"
    history = _read_json(target, {"observations": []})
    return [row for row in history.get("observations", []) if row.get("part_id") == part_id]


def landed_cost_cad(listing: Listing, fx: dict[str, float], *, tax_rate: float = 0.12, duty_rate: float = 0.0, brokerage_cad: float = 0.0) -> dict[str, float]:
    currency = listing.currency.upper()
    shipping_currency = (listing.shipping_currency or currency).upper()
    if currency not in fx or shipping_currency not in fx:
        raise ValueError(f"missing CAD FX rate for {currency} or {shipping_currency}")
    item_cad = listing.price * fx[currency]
    shipping_cad = (listing.shipping or 0.0) * fx[shipping_currency]
    customs_value = item_cad
    duty = customs_value * duty_rate
    taxable = item_cad + shipping_cad + duty + brokerage_cad
    tax = taxable * tax_rate
    return {"item_cad": round(item_cad, 2), "shipping_cad": round(shipping_cad, 2), "duty_cad": round(duty, 2), "brokerage_cad": round(brokerage_cad, 2), "tax_cad": round(tax, 2), "landed_cad": round(taxable + tax, 2)}


def load_fx(path: Path | None = None) -> dict[str, float]:
    target = path or project_root() / "data" / "market" / "fx-cad.json"
    payload = _read_json(target, {"rates_to_cad": {"CAD": 1.0}})
    rates = {str(k).upper(): float(v) for k, v in payload.get("rates_to_cad", {}).items()}
    rates["CAD"] = 1.0
    return rates


def ingest_performance(records: list[dict[str, Any]], path: Path | None = None) -> dict[str, int]:
    target = path or project_root() / "data" / "evidence" / "performance.json"
    payload = _read_json(target, {"schema_version": 1, "records": []})
    existing = {row["id"] for row in payload["records"]}
    added = 0
    for record in records:
        required = {"id", "part_id", "source_type", "source_url", "model", "runtime", "workload", "metric", "value", "unit"}
        missing = sorted(required - record.keys())
        if missing:
            raise ValueError(f"performance record missing: {', '.join(missing)}")
        if record["source_type"] not in PERF_SOURCE:
            raise ValueError(f"unsupported source_type: {record['source_type']}")
        if record["id"] in existing:
            continue
        normalized = dict(record)
        normalized["ingested_at"] = record.get("ingested_at") or _now()
        normalized["confidence"] = round(PERF_SOURCE[record["source_type"]] * float(record.get("reproducibility", 1.0)), 3)
        payload["records"].append(normalized); existing.add(record["id"]); added += 1
    _write_json(target, payload)
    return {"added": added, "total": len(payload["records"])}


def _compatibility_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("model", "model_variant", "quantization", "model_hash", "runtime", "backend", "workload", "metric", "unit", "context_length", "prompt_tokens", "generation_tokens", "batch_size", "hardware_configuration")
    return tuple(json.dumps(record.get(key), sort_keys=True) if isinstance(record.get(key), (dict, list)) else record.get(key) for key in keys)


def aggregate_performance(part_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "evidence" / "performance.json"
    payload = _read_json(target, {"records": []})
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in payload.get("records", []):
        if record.get("part_id") != part_id or record.get("source_type") not in MEASURED_SOURCES:
            continue
        groups.setdefault(_compatibility_signature(record), []).append(record)
    output: list[dict[str, Any]] = []
    for signature, rows in groups.items():
        values = [float(row["value"]) for row in rows]
        output.append({
            "signature": signature,
            "count": len(rows),
            "independent_sources": len({row.get("source_url") for row in rows}),
            "median": statistics.median(values),
            "mean": statistics.fmean(values),
            "min": min(values),
            "max": max(values),
            "average_confidence": statistics.fmean(float(row.get("confidence", 0.0)) for row in rows),
            "record_ids": [row.get("id") for row in rows],
        })
    return output
