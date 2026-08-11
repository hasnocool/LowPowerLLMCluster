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


async def discover_with_status(adapters: Iterable[DiscoveryAdapter], queries: list[str]) -> tuple[list[Listing], list[dict[str, Any]]]:
    active = [adapter for adapter in adapters if bool(getattr(adapter, "enabled", True))]
    groups = await asyncio.gather(*(adapter.discover(queries) for adapter in active), return_exceptions=True)
    listings: list[Listing] = []
    status: list[dict[str, Any]] = []
    for adapter, result in zip(active, groups, strict=True):
        if isinstance(result, BaseException):
            status.append({"source": adapter.name, "ok": False, "count": 0, "error": f"{type(result).__name__}: {result}"})
            continue
        listings.extend(result)
        status.append({"source": adapter.name, "ok": True, "count": len(result), "error": None})
    deduped = {(item.source, item.source_id): item for item in listings}
    return list(deduped.values()), status


async def discover_all(adapters: Iterable[DiscoveryAdapter], queries: list[str]) -> list[Listing]:
    listings, _ = await discover_with_status(adapters, queries)
    return listings


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


def seller_confidence(listing: Listing) -> dict[str, Any]:
    metrics = listing.seller_metrics or {}
    source_base = {"manufacturer": 0.95, "authorized_distributor": 0.92, "structured_marketplace": 0.42, "unknown": 0.3}.get(listing.source_kind, 0.3)
    score = source_base
    reasons = [f"source_kind={listing.source_kind}"]
    if metrics.get("verified_source"):
        score = max(score, 0.9); reasons.append("verified source")
    feedback_percentage = metrics.get("feedback_percentage")
    feedback_score = metrics.get("feedback_score")
    if feedback_percentage is not None:
        pct = max(0.0, min(float(feedback_percentage), 100.0)) / 100.0
        score = (score * 0.7) + (pct * 0.3); reasons.append(f"feedback={pct * 100:.2f}%")
    if feedback_score is not None and float(feedback_score) > 0:
        volume = min(1.0, math.log10(float(feedback_score) + 1) / 5.0)
        score = (score * 0.9) + (volume * 0.1); reasons.append(f"feedback_score={int(float(feedback_score))}")
    if metrics.get("top_rated"):
        score = min(1.0, score + 0.05); reasons.append("top-rated buying experience")
    score = round(max(0.0, min(score, 1.0)), 3)
    label = "exact" if score >= 0.94 else "high" if score >= 0.78 else "medium" if score >= 0.55 else "low"
    return {"score": score, "label": label, "reasons": reasons}


def match_listing(parts: list[dict[str, Any]], listing: Listing) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    ranked = sorted(((configuration_confidence(part, listing), part) for part in parts), key=lambda row: row[0]["score"], reverse=True)
    if not ranked or ranked[0][0]["score"] < 0.35:
        return None, {"score": 0.0, "label": "unknown"}
    confidence, part = ranked[0]
    return part, confidence


def append_price_observations(listings: list[Listing], parts: list[dict[str, Any]], path: Path | None = None) -> dict[str, int]:
    target = path or project_root() / "data" / "market" / "price-history.json"
    history = _read_json(target, {"schema_version": 1, "observations": []})
    observations = history.setdefault("observations", [])
    existing = {(row["source"], row["source_id"], row["observed_at"], row["price"], row["currency"]) for row in observations}
    added = 0
    for listing in listings:
        part, confidence = match_listing(parts, listing)
        row = {**asdict(listing), "part_id": part.get("id") if part else None, "configuration_confidence": confidence, "seller_confidence": seller_confidence(listing)}
        key = (row["source"], row["source_id"], row["observed_at"], row["price"], row["currency"])
        if key not in existing:
            observations.append(row); existing.add(key); added += 1
    observations.sort(key=lambda row: row["observed_at"])
    _write_json(target, history)
    return {"added": added, "total": len(observations)}


def update_listing_presence(listings: list[Listing], successful_sources: list[str], queries: list[str], path: Path | None = None, observed_at: str | None = None) -> dict[str, int]:
    """Track disappearance/reappearance only inside the same successful source + query scope."""
    target = path or project_root() / "data" / "market" / "listing-state.json"
    payload = _read_json(target, {"schema_version": 1, "states": {}, "events": []})
    states = payload.setdefault("states", {}); events = payload.setdefault("events", [])
    when = observed_at or _now(); scope = watch_scope(queries)
    current = {(item.source, item.source_id) for item in listings if item.source in successful_sources}
    counts = {"discovered": 0, "reappeared": 0, "disappeared": 0}

    for item in listings:
        if item.source not in successful_sources:
            continue
        key = f"{item.source}|{scope}|{item.source_id}"
        prior = states.get(key)
        event_type = None
        if prior is None:
            event_type = "discovered"
        elif not prior.get("active", True):
            event_type = "reappeared"
        states[key] = {"source": item.source, "source_id": item.source_id, "scope": scope, "url": item.url, "title": item.title, "active": True, "first_seen": prior.get("first_seen", when) if prior else when, "last_seen": when, "availability": item.availability}
        if event_type:
            events.append({"event": event_type, "source": item.source, "source_id": item.source_id, "scope": scope, "observed_at": when, "url": item.url}); counts[event_type] += 1

    for key, state in list(states.items()):
        if state.get("source") not in successful_sources or state.get("scope") != scope or not state.get("active", True):
            continue
        if (state["source"], state["source_id"]) not in current:
            state["active"] = False; state["last_missing"] = when
            events.append({"event": "disappeared", "source": state["source"], "source_id": state["source_id"], "scope": scope, "observed_at": when, "url": state.get("url")}); counts["disappeared"] += 1
    _write_json(target, payload)
    return counts


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


async def refresh_bank_of_canada_fx(currencies: list[str] | None = None, *, fx_path: Path | None = None, history_path: Path | None = None) -> dict[str, Any]:
    import httpx
    currencies = [code.upper() for code in (currencies or ["USD", "EUR", "GBP", "JPY", "CNY", "AUD"])]
    currencies = [code for code in currencies if code != "CAD"]
    series = [f"FX{code}CAD" for code in currencies]
    url = f"https://www.bankofcanada.ca/valet/observations/{','.join(series)}/json"
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url, params={"recent": 1}); response.raise_for_status(); payload = response.json()
    observations = payload.get("observations") or []
    if not observations:
        raise ValueError("Bank of Canada Valet returned no FX observations")
    observation = observations[-1]; rates = {"CAD": 1.0}
    for code, series_name in zip(currencies, series, strict=True):
        value = (observation.get(series_name) or {}).get("v")
        if value not in (None, ""):
            rates[code] = float(value)
    when = str(observation.get("d") or _now())
    source_url = str(response.url)
    fx_target = fx_path or project_root() / "data" / "market" / "fx-cad.json"
    history_target = history_path or project_root() / "data" / "market" / "fx-history.json"
    snapshot = {"schema_version": 1, "base": "CAD", "rates_to_cad": rates, "as_of": when, "source_url": source_url, "source": "Bank of Canada Valet API"}
    await asyncio.to_thread(_write_json, fx_target, snapshot)
    history = await asyncio.to_thread(_read_json, history_target, {"schema_version": 1, "snapshots": []})
    if not history["snapshots"] or history["snapshots"][-1].get("as_of") != when or history["snapshots"][-1].get("rates_to_cad") != rates:
        history["snapshots"].append(snapshot)
        await asyncio.to_thread(_write_json, history_target, history)
    return snapshot


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


def performance_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("model", "model_variant", "quantization", "model_hash", "runtime", "runtime_version", "backend", "workload", "metric", "unit", "context_length", "prompt_tokens", "generation_tokens", "batch_size", "hardware_config_id")
    return tuple(record.get(key) for key in keys)


def aggregate_compatible_performance(part_id: str, path: Path | None = None, *, measured_only: bool = True) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "evidence" / "performance.json"
    payload = _read_json(target, {"records": []})
    records = [row for row in payload.get("records", []) if row.get("part_id") == part_id]
    if measured_only:
        records = [row for row in records if row.get("source_type") in MEASURED_SOURCES]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in records:
        try:
            float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        groups.setdefault(performance_signature(row), []).append(row)
    output: list[dict[str, Any]] = []
    for signature, rows in groups.items():
        values = [float(row["value"]) for row in rows]
        confidences = [float(row.get("confidence", PERF_SOURCE.get(str(row.get("source_type")), 0.0))) for row in rows]
        output.append({"part_id": part_id, "signature": list(signature), "model": rows[0].get("model"), "runtime": rows[0].get("runtime"), "workload": rows[0].get("workload"), "metric": rows[0].get("metric"), "unit": rows[0].get("unit"), "count": len(rows), "sources": len({row.get("source_url") for row in rows}), "median": round(statistics.median(values), 6), "min": round(min(values), 6), "max": round(max(values), 6), "mean": round(statistics.fmean(values), 6), "mean_confidence": round(statistics.fmean(confidences), 3) if confidences else 0.0, "record_ids": [row.get("id") for row in rows]})
    return sorted(output, key=lambda row: (row["model"] or "", row["runtime"] or "", row["workload"] or "", row["metric"] or ""))
