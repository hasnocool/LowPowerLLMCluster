from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .catalog import load_catalog, project_root
from .compatibility import construct_compatible_builds, infer_listing_facts
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
    return _load(target, {"schema_version": 2, "components": {}, "sources": []})


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
    source_bonus = {"authorized_distributor": 0.12, "manufacturer": 0.15, "structured_marketplace": 0.0}.get(listing.source_kind, 0.0)
    quality = min(1.0, float(confidence["score"]) + source_bonus)
    facts = infer_listing_facts(component, listing.title, spec)
    return {
        "component": component,
        "listing": asdict(listing),
        "landed": landed,
        "seller_confidence": confidence,
        "compatibility": {"matched": True, "reasons": match_reasons},
        "compatibility_facts": facts,
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
    trusted = [row for row in filtered if (row.get("listing") or {}).get("source_kind") in {"authorized_distributor", "manufacturer"} and float(row["landed"]["landed_cad"]) <= cheapest_cost * (1.0 + preferred_pct / 100.0)]
    if trusted:
        trusted.sort(key=lambda row: (-float(row.get("quality_score") or 0.0), float(row["landed"]["landed_cad"])))
        return trusted[0]
    return max(filtered, key=lambda row: (float(row.get("quality_score") or 0.0) - min(float(row["landed"]["landed_cad"]) / max(cheapest_cost, 1.0) - 1.0, 1.0) * 0.25, -float(row["landed"]["landed_cad"])))


def _parse_when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _recent_gpu_listing(part_id: str, fx: dict[str, float], *, tax_rate: float, history_path: Path | None = None, max_age_hours: float = 168.0) -> dict[str, Any] | None:
    target = history_path or project_root() / "data" / "market" / "price-history.json"
    history = _load(target, {"observations": []})
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    candidates: list[dict[str, Any]] = []
    for row in history.get("observations", []):
        if row.get("part_id") != part_id:
            continue
        observed = _parse_when(row.get("observed_at"))
        if observed is None or observed < cutoff:
            continue
        config_score = float((row.get("configuration_confidence") or {}).get("score") or 0.0)
        seller_score = float((row.get("seller_confidence") or {}).get("score") or 0.0)
        if config_score < 0.5 or seller_score < 0.45:
            continue
        try:
            listing = Listing.from_mapping(row, str(row.get("source") or "market"))
            landed = landed_cost_cad(listing, fx, tax_rate=tax_rate)
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append({
            "listing": asdict(listing),
            "landed": landed,
            "configuration_confidence": row.get("configuration_confidence"),
            "seller_confidence": row.get("seller_confidence"),
        })
    if not candidates:
        return None
    candidates.sort(key=lambda item: float(item["landed"]["landed_cad"]))
    return candidates[0]


def _write_compatible_builds(output: dict[str, Any], config: dict[str, Any], fx: dict[str, float], *, tax_rate: float, path: Path | None = None) -> dict[str, Any]:
    selection = config.get("selection") or {}
    solver = config.get("build_solver") or {}
    result: dict[str, Any] = {"schema_version": 1, "generated_at": output["generated_at"], "currency": "CAD", "gpus": {}}
    gpu_parts = [part for part in load_catalog()["parts"] if part.get("category") == "gpu_accelerator"]
    for gpu in gpu_parts:
        gpu_id = str(gpu["id"])
        gpu_market = _recent_gpu_listing(gpu_id, fx, tax_rate=tax_rate)
        builds = construct_compatible_builds(
            output["components"],
            gpu_part=gpu,
            required_components=list(solver.get("required_components") or []),
            max_candidates_per_component=int(selection.get("max_candidates_per_component_for_build_solver", 5)),
            maximum_builds=int(selection.get("maximum_compatible_builds", 25)),
            allow_provisional=bool(selection.get("allow_provisional_compatibility", True)),
        )
        gpu_cost = float((gpu_market or {}).get("landed", {}).get("landed_cad") or 0.0) if gpu_market else None
        for build in builds:
            build["gpu"] = {"part_id": gpu_id, "name": gpu.get("name"), "market": gpu_market}
            build["complete_build_acquisition_cad"] = round(float(build["component_landed_cad"]) + gpu_cost, 2) if gpu_cost is not None else None
        builds.sort(key=lambda row: (row["complete_build_acquisition_cad"] is None, row["complete_build_acquisition_cad"] or 1e99, row["ranking_cost_cad"]))
        result["gpus"][gpu_id] = {
            "name": gpu.get("name"),
            "gpu_market": gpu_market,
            "build_count": len(builds),
            "best_build": builds[0] if builds else None,
            "builds": builds,
        }
    target = path or project_root() / "data" / "market" / "compatible-builds.json"
    _write(target, result)
    return result


async def refresh_bom_market(*, config_path: Path | None = None, output_path: Path | None = None, history_path: Path | None = None, builds_path: Path | None = None) -> dict[str, Any]:
    config = load_bom_config(config_path)
    fx = load_fx()
    tax_rate = float(config.get("tax_rate", 0.12))
    sources = [str(name) for name in config.get("sources", [])]
    output: dict[str, Any] = {"schema_version": 2, "generated_at": _now(), "currency": "CAD", "components": {}, "source_status": []}
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
        output["components"][component] = {"description": spec.get("description"), "selected": selected, "candidate_count": len(candidates), "candidates": candidates, "statuses": statuses}
        for row in candidates:
            listing = row["listing"]
            observations.append({"observed_at": output["generated_at"], "component": component, "source": listing.get("source"), "source_id": listing.get("source_id"), "url": listing.get("url"), "title": listing.get("title"), "native_price": listing.get("price"), "native_currency": listing.get("currency"), "landed_cad": row["landed"]["landed_cad"], "seller_confidence": row["seller_confidence"], "compatibility_facts": row.get("compatibility_facts"), "selected": bool(selected and selected["listing"]["source"] == listing.get("source") and selected["listing"]["source_id"] == listing.get("source_id"))})
    observations[:] = observations[-10000:]
    _write(history_target, history)
    target = output_path or project_root() / "data" / "market" / "bom-current.json"
    _write(target, output)
    compatible = _write_compatible_builds(output, config, fx, tax_rate=tax_rate, path=builds_path)
    output["compatible_builds"] = {gpu_id: {"build_count": row["build_count"], "best_build_acquisition_cad": (row.get("best_build") or {}).get("complete_build_acquisition_cad")} for gpu_id, row in compatible["gpus"].items()}
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
        evidence[str(component)] = {"basis": "sourced_live_listing_landed_cad", "observed_at": payload.get("generated_at"), "source": listing.get("source"), "source_kind": listing.get("source_kind"), "seller": listing.get("seller"), "url": listing.get("url"), "title": listing.get("title"), "seller_confidence": selected.get("seller_confidence"), "compatibility_facts": selected.get("compatibility_facts")}
    return costs, evidence
