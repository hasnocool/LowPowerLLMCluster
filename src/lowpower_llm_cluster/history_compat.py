from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from .active_records import active_records
from .live_discoveries import LIVE_DISCOVERIES_HTML, query_live
from .promotion_state import STATES, filter_promotion_items, project_promotion_records
from .source_observability import read_source_health

EXPECTED_TABLES = {"observations", "listing_state", "refresh_runs"}


def probe_history(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "compatible": False, "database_exists": False, "missing_tables": sorted(EXPECTED_TABLES)}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        connection.close()
    except sqlite3.Error as exc:
        return {"path": str(path), "compatible": False, "database_exists": True, "database_error": str(exc)}
    missing = sorted(EXPECTED_TABLES - tables)
    return {"path": str(path), "compatible": not missing, "database_exists": True, "missing_tables": missing}


def history_candidates(configured: Path) -> list[Path]:
    configured = configured.expanduser().resolve()
    candidates = [configured, configured.parent / "catalog-history.sqlite3"]
    for parent in list(configured.parents)[:4]:
        candidates.append(parent / "results" / "catalog-history.sqlite3")
    candidates.append(Path("results/catalog-history.sqlite3").resolve())
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved); result.append(resolved)
    return result


def select_history(configured: Path) -> Path | None:
    for candidate in history_candidates(configured):
        if probe_history(candidate).get("compatible"):
            return candidate
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return payload if isinstance(payload, dict) else {}


def _parse_time(value: Any) -> datetime | None:
    if not value: return None
    try: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError: return None
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _promotion_health(path: Path, latest_run: dict[str, Any] | None) -> dict[str, Any]:
    health = _load_json(path)
    promotion_at = _parse_time(health.get("promotion_completed_at"))
    run_at = _parse_time((latest_run or {}).get("completed_at"))
    stale = bool(run_at and (promotion_at is None or promotion_at < run_at))
    value = dict(health)
    value["exists"] = path.exists()
    value["promotion_stale"] = stale
    value["promotion_fresh"] = bool(health.get("status") == "ok" and not stale)
    return value


def _live_shell(html: str) -> str:
    shell = r'''
<style>#lpllm-runtime-block{margin:0 0 18px}#lpllm-runtime-head{display:flex;justify-content:space-between;gap:12px;align-items:end;margin:0 0 10px}#lpllm-runtime-head h2{margin:0;font-size:17px}#lpllm-runtime-head a{font-size:12px}</style>
<script>(()=>{function install(){const first=document.querySelector('.stats');if(!first||document.getElementById('lpllm-runtime-block'))return;const block=document.createElement('section');block.id='lpllm-runtime-block';block.innerHTML=`<div id="lpllm-runtime-head"><div><div class="eyebrow">Runtime staging</div><h2>Discovery & canonical promotion</h2></div><a href="/discoveries">Review promotion pipeline →</a></div><div class="stats"><div class="stat"><div class="statlabel">Live discoveries</div><div class="statvalue" id="lpa">0</div></div><div class="stat"><div class="statlabel">Held</div><div class="statvalue" id="lph">0</div></div><div class="stat"><div class="statlabel">Promotion ready</div><div class="statvalue" id="lpr">0</div></div><div class="stat"><div class="statlabel">Auto canonical</div><div class="statvalue" id="lpc">0</div></div></div>`;first.parentNode.insertBefore(block,first)}async function update(){install();try{const [s,p]=await Promise.all([fetch('/api/state',{cache:'no-store'}).then(r=>r.json()),fetch('/api/promotion-state?limit=1',{cache:'no-store'}).then(r=>r.json())]);lpa.textContent=s.active_listings||0;lph.textContent=p.counts?.held||0;lpr.textContent=p.counts?.promotion_ready||0;lpc.textContent=p.counts?.canonical||0;}catch(_){}}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',update);else update();setInterval(update,5000)})();</script>
'''
    return html.replace("</body>", shell + "</body>") if "</body>" in html else html + shell


def main() -> int:
    from . import dashboard_service as dashboard

    parser = dashboard.build_parser()
    parser.add_argument("--discovery-output", default="results/discovery-latest.json")
    parser.add_argument("--promotion-report", default="results/promotion-latest.json")
    parser.add_argument("--promotion-catalog", default="data/catalog/auto-promoted.json")
    parser.add_argument("--promotion-health", default="results/promotion-health.json")
    args = parser.parse_args()

    original_state = dashboard._history_state_sync
    original_shell = dashboard._inject_live_shell
    original_health = dashboard._health

    configured_history = Path(args.history).expanduser().resolve()
    discovery_path = Path(args.discovery_output).expanduser().resolve()
    report_path = Path(args.promotion_report).expanduser().resolve()
    catalog_path = Path(args.promotion_catalog).expanduser().resolve()
    health_path = Path(args.promotion_health).expanduser().resolve()

    def compatible_state(configured: Path) -> dict[str, Any]:
        candidate = select_history(configured)
        if candidate is not None:
            state = original_state(candidate)
            state["configured_history_path"] = str(configured)
            state["history_path"] = str(candidate)
            state["auto_selected_history"] = candidate != configured
            state["schema_status"] = "live_history"
            try: state["database_bytes"] = candidate.stat().st_size
            except OSError: state["database_bytes"] = None
            if state.get("latest_run") is None: state["latest_run"] = {"status": "waiting_for_scanner"}
            state["promotion"] = _promotion_health(health_path, state.get("latest_run"))
            return state
        info = probe_history(configured)
        status = "misconfigured" if info.get("database_exists") else "disconnected"
        return {"database_exists": bool(info.get("database_exists")), "observations": 0, "active_listings": 0, "max_observation_id": 0, "latest_run": {"status": status}, "recent": [], "scanner_status": status, "schema_status": "legacy_or_incompatible" if info.get("database_exists") else "missing", "missing_tables": info.get("missing_tables", []), "configured_history_path": str(configured), "history_path": None, "promotion": _promotion_health(health_path, None)}

    async def discoveries_page(_: web.Request) -> web.Response:
        return web.Response(text=LIVE_DISCOVERIES_HTML, content_type="text/html", headers={"Cache-Control": "no-store"})

    async def discoveries_api(request: web.Request) -> web.Response:
        candidate = select_history(configured_history)
        if candidate is None:
            return web.json_response({"path": None, "total": 0, "sources": [], "items": [], "error": "live history database is not connected"}, status=503)
        try:
            limit = min(1000, max(1, int(request.query.get("limit", "200")))); offset = max(0, int(request.query.get("offset", "0")))
        except ValueError: limit, offset = 200, 0
        return web.json_response(await query_live(candidate, limit=limit, offset=offset, query=request.query.get("q", "").strip(), source=request.query.get("source", "").strip()))

    async def promotion_api(request: web.Request) -> web.Response:
        candidate = select_history(configured_history)
        if candidate is None:
            return web.json_response({"total": 0, "sources": [], "counts": {state: 0 for state in STATES}, "reason_counts": {}, "items": [], "error": "live history database is not connected"}, status=503)
        try:
            limit = min(2000, max(1, int(request.query.get("limit", "500")))); offset = max(0, int(request.query.get("offset", "0")))
        except ValueError: limit, offset = 500, 0
        live = await active_records(candidate)
        report, catalog = await asyncio.gather(asyncio.to_thread(_load_json, report_path), asyncio.to_thread(_load_json, catalog_path))
        snapshot = await asyncio.to_thread(project_promotion_records, live["items"], report=report, catalog=catalog)
        filtered = filter_promotion_items(snapshot["items"], state=request.query.get("state", ""), reason=request.query.get("reason", ""), query=request.query.get("q", ""), source=request.query.get("source", ""))
        snapshot["sources"] = live["sources"]
        snapshot["filtered_total"] = len(filtered)
        snapshot["items"] = filtered[offset:offset+limit]
        snapshot["limit"] = limit; snapshot["offset"] = offset
        snapshot["promotion_health"] = _promotion_health(health_path, compatible_state(configured_history).get("latest_run"))
        snapshot["paths"] = {"discovery": str(discovery_path), "report": str(report_path), "catalog": str(catalog_path), "health": str(health_path)}
        return web.json_response(snapshot)

    async def source_health_api(_: web.Request) -> web.Response:
        candidate = select_history(configured_history)
        if candidate is None: return web.json_response({"total": 0, "summary": {}, "sources": []}, status=503)
        return web.json_response(await read_source_health(candidate, report_path))

    async def promotion_health_api(_: web.Request) -> web.Response:
        state = compatible_state(configured_history)
        return web.json_response(state.get("promotion") or {})

    async def compatible_health(request: web.Request) -> web.Response:
        base = await original_health(request)
        state = compatible_state(configured_history)
        promotion = state.get("promotion") or {}
        payload = json.loads(base.text) if base.text else {}
        payload["promotion"] = promotion
        degraded = base.status >= 400 or not promotion.get("promotion_fresh", False)
        payload["status"] = "degraded" if degraded else "ok"
        return web.json_response(payload, status=503 if degraded else 200)

    dashboard._history_state_sync = compatible_state
    dashboard._inject_live_shell = lambda html: _live_shell(original_shell(html))
    dashboard._health = compatible_health
    app = dashboard.create_dashboard_app(output=args.output, history=args.history, event_log=args.event_log, refresh_interval=args.refresh_interval, db_poll=args.db_poll)
    app.router.add_get("/discoveries", discoveries_page)
    app.router.add_get("/api/discoveries", discoveries_api)
    app.router.add_get("/api/promotion-state", promotion_api)
    app.router.add_get("/api/source-health", source_health_api)
    app.router.add_get("/api/promotion-health", promotion_health_api)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__": raise SystemExit(main())
