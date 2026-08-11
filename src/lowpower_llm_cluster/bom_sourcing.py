from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import project_root
from .market import Listing, landed_cost_cad, load_fx, seller_confidence
from .sources import DigiKeyAdapter, EbayBrowseAdapter, MouserAdapter


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_bom_config(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "market" / "bom-sourcing.json"
    return _load(target, {"schema_version": 1, "components": {}, "sources": []})


def _adapter(name: str):
    if name == "mouser":
        return MouserAdapter()
    if name == "digikey":
        return DigiKeyAdapter()
    if name == "ebay":
        return EbayBrowseAdapter()
    raise KeyError(name)


def _matches(title: str, spec: dict[str, Any]) -> tuple[bool, list[str]]:
    text = " ".join(title.casefold().split())
    reasons: list[str] = []
    excluded = [term.casefold() for term in spec.get("exclude_terms", [])]
    for term in excluded:
        if term and term in text:
            return False, [f"excluded:{term}"]
    required_any = [term.casefold() for term in spec.get("required_terms_any", [])]
    if required_any and not any(term in text for term in required_any):
        return False, ["missing_required_term"]
    if required_any:
        reasons.append("required_term_match")
    return True, reasons


def rank_bom_listing(component: str, listing: Listing, spec: dict[str, Any], fx: dict[str, float], *, tax_rate: float) -> dict[str, Any] | None:
    matched, match_reasons = _matches(listing.title, spec)
    if not matched:
        return None
    confidence = seller_confidence(listing)
    try:
        landed = landed_cost_cad(listing, fx, tax_rate=tax_rate)
    except ValueError:
        return None
    source_bonus = {
        "authorized_distributor": 0.12,
        "manufacturer": 0.15,
        "structured_marketplace": 0.0,
    }.get(listing.source_kind, 0.0)
    quality = min(1.0, float(confidence["score"]) + source_bonus)
    return {
        "component": component,
        "listing": asdict(listing),
        "landed": landed,
        "seller_confidence": confidence,
        "compatibility": {"matched": True, "reasons": match_reasons},
        "quality_score": round(quality, 3),
    }


def select_bom_candidate(candidates: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any] | None:
    if not candidates:
        return None
    selection = config.get("selection") or {}
    minimum = float(selection.get("minimum_seller_confidence", 0.45))
    filtered = [row for row in candidates if float((row.get("seller_confidence") or {}).get("score") or 0.0) >= minimum]
    if not filtered:
        return None
    filtered.sort(key=lambda row: float((row.get("landed") or {}).get("landed_cad") or 1e99))
    cheapest = filtered[0]
    preferred_pct = float(selection.get("prefer_authorized_sources_within_pct", 12.0))
    cheapest_cost = float(cheapest["landed"]["landed_cad"])
    trusted = [
        row for row in filtered
        if (row.get("listing") or {}).get("source_kind") in {"authorized_distributor", "manufacturer"}
        and float(row["landed"]["landed_cad"]) <= cheapest_cost * (1.0 + preferred_pct / 100.0)
    ]
    if trusted:
        trusted.sort(key=lambda row: (-float(row.get("quality_score") or 0.0), float(row["landed"]["landed_cad"])))
        return trusted[0]
    return max(
        filtered,
        key=lambda row: (
            float(row.get("quality_score") or 0.0) - min(float(row["landed"]["landed_cad"]) / max(cheapest_cost, 1.0) - 1.0, 1.0) * 0.25,
            -float(row["landed"]["landed_cad"]),
        ),
    )


async def refresh_bom_market(*, config_path: Path | None = None, output_path: Path | None = None, history_path: Path | None = None) -> dict[str, Any]:
    config = load_bom_config(config_path)
    fx = load_fx()
    tax_rate = float(config.get("tax_rate", 0.12))
    sources = [str(name) for name in config.get("sources", [])]
    output: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _now(),
        "currency": "CAD",
        "components": {},
        "source_status": [],
    }
    history_target = history_path or project_root() / "data" / "market" / "bom-price-history.json"
    history = _load(history_target, {"schema_version": 1, "observations": []})
    observations = history.setdefault("observations", [])

    for component, spec in (config.get("components") or {}).items():
        candidates: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        queries = list(spec.get("queries", []))
        for source in sources:
            adapter = _adapter(source)
            if not bool(getattr(adapter, "enabled", True)):
                statuses.append({"source": source, "enabled": False, "ok": True, "count": 0, "reason": "credentials_not_configured"})
                continue
            try:
                listings = await adapter.discover(queries)
            except Exception as exc:
                statuses.append({"source": source, "enabled": True, "ok": False, "count": 0, "error": f"{type(exc).__name__}: {exc}"})
                continue
            statuses.append({"source": source, "enabled": True, "ok": True, "count": len(listings)})
            for listing in listings:
                ranked = rank_bom_listing(component, listing, spec, fx, tax_rate=tax_rate)
                if ranked is not None:
                    candidates.append(ranked)
        candidates.sort(key=lambda row: float(row["landed"]["landed_cad"]))
        limit = int((config.get("selection") or {}).get("maximum_results_per_component", 12))
        candidates = candidates[:limit]
        selected = select_bom_candidate(candidates, config)
        output["components"][component] = {
            "description": spec.get("description"),
            "selected": selected,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "statuses": statuses,
        }
        for row in candidates:
            listing = row["listing"]
            observations.append({
                "observed_at": output["generated_at"],
                "component": component,
                "source": listing.get("source"),
                "source_id": listing.get("source_id"),
                "url": listing.get("url"),
                "title": listing.get("title"),
                "native_price": listing.get("price"),
                "native_currency": listing.get("currency"),
                "landed_cad": row["landed"]["landed_cad"],
                "seller_confidence": row["seller_confidence"],
                "selected": bool(selected and selected["listing"]["source"] == listing.get("source") and selected["listing"]["source_id"] == listing.get("source_id")),
            })
    observations[:] = observations[-10000:]
    _write(history_target, history)
    target = output_path or project_root() / "data" / "market" / "bom-current.json"
    _write(target, output)
    return output


def sourced_component_costs(path: Path | None = None) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    target = path or project_root() / "data" / "market" / "bom-current.json"
    payload = _load(target, {"components": {}})
    costs: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for component, row in (payload.get("components") or {}).items():
        selected = row.get("selected") or {}
        landed = selected.get("landed") or {}
        value = landed.get("landed_cad")
        if value is None:
            continue
        costs[str(component)] = float(value)
        listing = selected.get("listing") or {}
        evidence[str(component)] = {
            "basis": "sourced_live_listing_landed_cad",
            "observed_at": payload.get("generated_at"),
            "source": listing.get("source"),
            "source_kind": listing.get("source_kind"),
            "seller": listing.get("seller"),
            "url": listing.get("url"),
            "title": listing.get("title"),
            "seller_confidence": selected.get("seller_confidence"),
        }
    return costs, evidence
