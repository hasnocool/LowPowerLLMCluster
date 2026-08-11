# src/lowpower_llm_cluster/ops.py
from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from .bom_sourcing import refresh_bom_market
from .catalog import load_catalog, project_root
from .decision import generate_daily_recommendations, render_daily_recommendations
from .intelligence import generate_change_intelligence, render_daily_change_report
from .market import append_price_observations, discover_with_status, refresh_bank_of_canada_fx, update_listing_presence
from .power_ingestion import refresh_power_evidence
from .reports import build_report_rows, named_reports, render_report
from .sources import DigiKeyAdapter, EbayBrowseAdapter, ManufacturerJsonLdAdapter, MouserAdapter
from .tco import apply_tco_to_summary, render_tco_report


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists(): return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); tmp.replace(path)


async def with_retry(operation: Callable[[], Awaitable[Any]], *, attempts: int = 4, base_delay_s: float = 1.0, max_delay_s: float = 30.0) -> Any:
    last: BaseException | None = None
    for attempt in range(attempts):
        try: return await operation()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                if status not in {408, 425, 429, 500, 502, 503, 504}: raise
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    try: delay = min(max_delay_s, max(0.0, float(retry_after)))
                    except ValueError: delay = min(max_delay_s, base_delay_s * (2**attempt))
                else: delay = min(max_delay_s, base_delay_s * (2**attempt))
            else: delay = min(max_delay_s, base_delay_s * (2**attempt))
            delay *= 0.9 + random.random() * 0.2
            if attempt + 1 < attempts: await asyncio.sleep(delay)
    assert last is not None
    raise last


class RetryingAdapter:
    def __init__(self, adapter: Any, retry: dict[str, Any], *, source_key: str, max_queries: int | None = None) -> None:
        self.adapter = adapter; self.name = adapter.name; self.source_key = source_key; self.enabled = bool(getattr(adapter, "enabled", True)); self.retry = retry; self.max_queries = max_queries
    async def discover(self, queries: list[str]):
        selected = queries[: self.max_queries] if self.max_queries is not None else queries
        return await with_retry(lambda: self.adapter.discover(selected), attempts=int(self.retry.get("attempts", 4)), base_delay_s=float(self.retry.get("base_delay_s", 1.0)), max_delay_s=float(self.retry.get("max_delay_s", 30.0)))


def _budget_state(path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    target = path or project_root() / "data" / "market" / "source-budgets.json"; today = datetime.now(UTC).date().isoformat(); payload = _load(target, {"schema_version": 1, "date": today, "sources": {}})
    if payload.get("date") != today: payload = {"schema_version": 1, "date": today, "sources": {}}
    return target, payload


def reserve_source_budget(source: str, requested: int, budget: dict[str, Any], *, path: Path | None = None) -> tuple[int, dict[str, Any]]:
    target, payload = _budget_state(path); state = payload["sources"].setdefault(source, {"estimated_requests": 0, "skipped": 0}); daily_limit = int(budget.get("daily_request_budget", 1000000)); per_run = int(budget.get("max_queries_per_run", requested)); remaining = max(0, daily_limit - int(state.get("estimated_requests", 0))); allowed = min(requested, per_run, remaining)
    state["estimated_requests"] = int(state.get("estimated_requests", 0)) + allowed
    if allowed < requested: state["skipped"] = int(state.get("skipped", 0)) + (requested - allowed)
    state["last_reserved_at"] = _now(); _write(target, payload)
    return allowed, {"requested": requested, "allowed": allowed, "daily_limit": daily_limit, "remaining_after": max(0, remaining - allowed)}


def adapters_for_profile(profile: dict[str, Any], sources_config: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    adapters: list[Any] = []; budget_status: dict[str, Any] = {}; budgets = profile.get("source_budgets") or {}; queries = list(profile.get("queries", []))
    for source in profile.get("sources", []):
        if source == "manufacturer": adapter = ManufacturerJsonLdAdapter(list(sources_config.get("manufacturer_jsonld_urls", [])))
        elif source == "mouser": adapter = MouserAdapter()
        elif source == "digikey": adapter = DigiKeyAdapter()
        elif source == "ebay": adapter = EbayBrowseAdapter()
        else: continue
        budget = budgets.get(source, {}); allowed, status = reserve_source_budget(source, len(queries), budget); budget_status[source] = status; wrapped = RetryingAdapter(adapter, profile.get("retry") or {}, source_key=source, max_queries=allowed)
        if allowed <= 0: wrapped.enabled = False
        adapters.append(wrapped)
    return adapters, budget_status


def record_source_health(statuses: list[dict[str, Any]], *, profile: str, elapsed_s: float, path: Path | None = None) -> None:
    target = path or project_root() / "data" / "market" / "source-health.json"; payload = _load(target, {"schema_version": 1, "sources": {}, "history": []}); when = _now()
    for row in statuses:
        source = row["source"]; current = payload["sources"].get(source, {"consecutive_failures": 0})
        if row["ok"]: current["consecutive_failures"] = 0; current["last_success"] = when; current["last_count"] = row["count"]
        else: current["consecutive_failures"] = int(current.get("consecutive_failures", 0)) + 1; current["last_failure"] = when; current["last_error"] = row.get("error")
        current["last_checked"] = when; payload["sources"][source] = current; payload["history"].append({"observed_at": when, "profile": profile, "elapsed_s": round(elapsed_s, 3), **row})
    payload["history"] = payload["history"][-2000:]; _write(target, payload)


def stale_listings(*, stale_after_hours: float = 48.0, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "market" / "listing-state.json"; payload = _load(target, {"states": {}}); cutoff = datetime.now(UTC) - timedelta(hours=stale_after_hours); rows: list[dict[str, Any]] = []
    for state in payload.get("states", {}).values():
        if not state.get("active", True) or not state.get("last_seen"): continue
        try: seen = datetime.fromisoformat(str(state["last_seen"]).replace("Z", "+00:00"))
        except ValueError: continue
        if seen < cutoff:
            age_h = (datetime.now(UTC) - seen).total_seconds() / 3600; rows.append({**state, "stale_hours": round(age_h, 1)})
    return sorted(rows, key=lambda row: row["stale_hours"], reverse=True)


def write_current_reports(*, output_dir: Path | None = None, tax_rate: float = 0.12) -> dict[str, int]:
    out = output_dir or project_root() / "reports" / "current"; out.mkdir(parents=True, exist_ok=True); rows = build_report_rows(load_catalog()["parts"], tax_rate=tax_rate); reports = named_reports(rows); manifest = {"generated_at": _now(), "tax_rate": tax_rate, "reports": {}}
    for name, items in reports.items():
        (out / f"{name}.md").write_text(render_report(items, name.replace("-", " ").title()) + "\n", encoding="utf-8"); (out / f"{name}.json").write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8"); manifest["reports"][name] = len(items)
    _write(out / "manifest.json", manifest); return {name: len(items) for name, items in reports.items()}


async def run_profile(name: str, *, profiles_path: Path | None = None, sources_path: Path | None = None) -> dict[str, Any]:
    profiles_path = profiles_path or project_root() / "data" / "market" / "profiles.json"; sources_path = sources_path or project_root() / "data" / "market" / "sources.json"; profiles = _load(profiles_path, {"profiles": {}}).get("profiles", {})
    if name not in profiles: raise KeyError(f"unknown refresh profile: {name}")
    profile = profiles[name]; sources = _load(sources_path, {}); adapters, budgets = adapters_for_profile(profile, sources); queries = list(profile.get("queries", []))
    started = time.monotonic(); listings, statuses = await discover_with_status(adapters, queries); elapsed = time.monotonic() - started; successful = [row["source"] for row in statuses if row["ok"]]; parts = load_catalog()["parts"]
    prices = await asyncio.to_thread(append_price_observations, listings, parts); presence = await asyncio.to_thread(update_listing_presence, listings, successful, queries); await asyncio.to_thread(record_source_health, statuses, profile=name, elapsed_s=elapsed)
    fx_result = None
    if profile.get("refresh_fx", False): fx_result = await with_retry(lambda: refresh_bank_of_canada_fx(profile.get("currencies")))
    bom_result = None
    if profile.get("refresh_bom", True):
        try:
            bom = await refresh_bom_market()
            bom_result = {component: {"candidates": row.get("candidate_count", 0), "selected_landed_cad": ((row.get("selected") or {}).get("landed") or {}).get("landed_cad"), "source": ((row.get("selected") or {}).get("listing") or {}).get("source")} for component, row in bom.get("components", {}).items()}
        except Exception as exc:
            bom_result = {"error": f"{type(exc).__name__}: {exc}"}
    power_result = None
    if profile.get("refresh_power_evidence", True):
        try: power_result = await asyncio.to_thread(refresh_power_evidence)
        except Exception as exc: power_result = {"error": f"{type(exc).__name__}: {exc}"}
    report_counts = None
    if profile.get("generate_reports", False): report_counts = await asyncio.to_thread(write_current_reports, tax_rate=float(profile.get("tax_rate", 0.12)))
    intelligence = await asyncio.to_thread(generate_change_intelligence, default_price_drop_pct=float(profile.get("price_drop_pct", 10.0)), default_landed_change_pct=float(profile.get("landed_cost_change_pct", 8.0)), default_benchmark_change_pct=float(profile.get("benchmark_change_pct", 10.0)), tax_rate=float(profile.get("tax_rate", 0.12)))
    daily_md = project_root() / "reports" / "current" / "daily-changes.md"; daily_md.parent.mkdir(parents=True, exist_ok=True); daily_md.write_text(render_daily_change_report(intelligence), encoding="utf-8")
    decisions = await asyncio.to_thread(generate_daily_recommendations, tax_rate=float(profile.get("tax_rate", 0.12))); tco_scenario = str(profile.get("tco_scenario", "mixed-3yr")); decisions = await asyncio.to_thread(apply_tco_to_summary, decisions, scenario_name=tco_scenario)
    recommendation_json = project_root() / "reports" / "current" / "daily-recommendations.json"; _write(recommendation_json, decisions); recommendation_md = project_root() / "reports" / "current" / "daily-recommendations.md"; recommendation_md.parent.mkdir(parents=True, exist_ok=True); recommendation_md.write_text(render_daily_recommendations(decisions), encoding="utf-8")
    tco_md = project_root() / "reports" / "current" / "daily-tco.md"; tco_md.write_text(render_tco_report(decisions), encoding="utf-8"); _write(project_root() / "reports" / "current" / "daily-tco.json", {"generated_at": decisions.get("generated_at"), "scenario": tco_scenario, "recommendations": decisions.get("recommendations", [])})
    stale = stale_listings(stale_after_hours=float(profile.get("stale_after_hours", 48))); result = {"profile": name, "listings": len(listings), "statuses": statuses, "source_budgets": budgets, "price_observations": prices, "presence": presence, "stale_count": len(stale), "fx": fx_result, "bom": bom_result, "power_evidence": power_result, "reports": report_counts, "change_alerts": intelligence.get("alert_count", 0), "recommendations": decisions.get("counts", {}), "priority_alerts": len(decisions.get("priority_alerts", [])), "new_all_time_lows": decisions.get("all_time_low_count", 0), "tco_scenario": tco_scenario}; _write(project_root() / "data" / "market" / "last-refresh.json", {"completed_at": _now(), **result}); return result
