# src/lowpower_llm_cluster/ops.py
from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from .catalog import load_catalog, project_root
from .market import append_price_observations, discover_with_status, refresh_bank_of_canada_fx, update_listing_presence
from .reports import build_report_rows, named_reports, render_report
from .sources import DigiKeyAdapter, EbayBrowseAdapter, ManufacturerJsonLdAdapter, MouserAdapter


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


async def with_retry(
    operation: Callable[[], Awaitable[Any]],
    *,
    attempts: int = 4,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
) -> Any:
    """Retry transient HTTP/network failures with exponential backoff and Retry-After support."""
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                if status not in {408, 425, 429, 500, 502, 503, 504}:
                    raise
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = min(max_delay_s, max(0.0, float(retry_after)))
                    except ValueError:
                        delay = min(max_delay_s, base_delay_s * (2**attempt))
                else:
                    delay = min(max_delay_s, base_delay_s * (2**attempt))
            else:
                delay = min(max_delay_s, base_delay_s * (2**attempt))
            delay *= 0.9 + random.random() * 0.2
            if attempt + 1 < attempts:
                await asyncio.sleep(delay)
    assert last is not None
    raise last


class RetryingAdapter:
    def __init__(self, adapter: Any, retry: dict[str, Any]) -> None:
        self.adapter = adapter
        self.name = adapter.name
        self.enabled = bool(getattr(adapter, "enabled", True))
        self.retry = retry

    async def discover(self, queries: list[str]):
        return await with_retry(
            lambda: self.adapter.discover(queries),
            attempts=int(self.retry.get("attempts", 4)),
            base_delay_s=float(self.retry.get("base_delay_s", 1.0)),
            max_delay_s=float(self.retry.get("max_delay_s", 30.0)),
        )


def adapters_for_profile(profile: dict[str, Any], sources_config: dict[str, Any]) -> list[Any]:
    adapters: list[Any] = []
    for source in profile.get("sources", []):
        if source == "manufacturer":
            adapters.append(ManufacturerJsonLdAdapter(list(sources_config.get("manufacturer_jsonld_urls", []))))
        elif source == "mouser":
            adapters.append(MouserAdapter())
        elif source == "digikey":
            adapters.append(DigiKeyAdapter())
        elif source == "ebay":
            adapters.append(EbayBrowseAdapter())
    retry = profile.get("retry") or {}
    return [RetryingAdapter(adapter, retry) for adapter in adapters]


def record_source_health(statuses: list[dict[str, Any]], *, profile: str, elapsed_s: float, path: Path | None = None) -> None:
    target = path or project_root() / "data" / "market" / "source-health.json"
    payload = _load(target, {"schema_version": 1, "sources": {}, "history": []})
    when = _now()
    for row in statuses:
        source = row["source"]
        current = payload["sources"].get(source, {"consecutive_failures": 0})
        if row["ok"]:
            current["consecutive_failures"] = 0
            current["last_success"] = when
            current["last_count"] = row["count"]
        else:
            current["consecutive_failures"] = int(current.get("consecutive_failures", 0)) + 1
            current["last_failure"] = when
            current["last_error"] = row.get("error")
        current["last_checked"] = when
        payload["sources"][source] = current
        payload["history"].append({"observed_at": when, "profile": profile, "elapsed_s": round(elapsed_s, 3), **row})
    payload["history"] = payload["history"][-2000:]
    _write(target, payload)


def stale_listings(*, stale_after_hours: float = 48.0, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "market" / "listing-state.json"
    payload = _load(target, {"states": {}})
    cutoff = datetime.now(UTC) - timedelta(hours=stale_after_hours)
    rows: list[dict[str, Any]] = []
    for state in payload.get("states", {}).values():
        if not state.get("active", True):
            continue
        last_seen = state.get("last_seen")
        if not last_seen:
            continue
        try:
            seen = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
        except ValueError:
            continue
        if seen < cutoff:
            age_h = (datetime.now(UTC) - seen).total_seconds() / 3600
            rows.append({**state, "stale_hours": round(age_h, 1)})
    return sorted(rows, key=lambda row: row["stale_hours"], reverse=True)


def write_current_reports(*, output_dir: Path | None = None, tax_rate: float = 0.12) -> dict[str, int]:
    out = output_dir or project_root() / "reports" / "current"
    out.mkdir(parents=True, exist_ok=True)
    rows = build_report_rows(load_catalog()["parts"], tax_rate=tax_rate)
    reports = named_reports(rows)
    manifest = {"generated_at": _now(), "tax_rate": tax_rate, "reports": {}}
    for name, items in reports.items():
        (out / f"{name}.md").write_text(render_report(items, name.replace("-", " ").title()) + "\n", encoding="utf-8")
        (out / f"{name}.json").write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["reports"][name] = len(items)
    _write(out / "manifest.json", manifest)
    return {name: len(items) for name, items in reports.items()}


async def run_profile(name: str, *, profiles_path: Path | None = None, sources_path: Path | None = None) -> dict[str, Any]:
    profiles_path = profiles_path or project_root() / "data" / "market" / "profiles.json"
    sources_path = sources_path or project_root() / "data" / "market" / "sources.json"
    profiles = _load(profiles_path, {"profiles": {}}).get("profiles", {})
    if name not in profiles:
        raise KeyError(f"unknown refresh profile: {name}")
    profile = profiles[name]
    sources = _load(sources_path, {})
    adapters = adapters_for_profile(profile, sources)
    queries = list(profile.get("queries", []))

    started = time.monotonic()
    listings, statuses = await discover_with_status(adapters, queries)
    elapsed = time.monotonic() - started
    successful = [row["source"] for row in statuses if row["ok"]]
    parts = load_catalog()["parts"]
    prices = await asyncio.to_thread(append_price_observations, listings, parts)
    presence = await asyncio.to_thread(update_listing_presence, listings, successful, queries)
    await asyncio.to_thread(record_source_health, statuses, profile=name, elapsed_s=elapsed)

    fx_result = None
    if profile.get("refresh_fx", False):
        fx_result = await with_retry(lambda: refresh_bank_of_canada_fx(profile.get("currencies")))

    report_counts = None
    if profile.get("generate_reports", False):
        report_counts = await asyncio.to_thread(write_current_reports, tax_rate=float(profile.get("tax_rate", 0.12)))

    stale = stale_listings(stale_after_hours=float(profile.get("stale_after_hours", 48)))
    result = {"profile": name, "listings": len(listings), "statuses": statuses, "price_observations": prices, "presence": presence, "stale_count": len(stale), "fx": fx_result, "reports": report_counts}
    _write(project_root() / "data" / "market" / "last-refresh.json", {"completed_at": _now(), **result})
    return result
