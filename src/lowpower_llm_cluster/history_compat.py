from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web

from .catalog import project_root
from .live_discoveries import LIVE_DISCOVERIES_HTML, query_live
from .promotion_state import STATES, build_promotion_snapshot, filter_promotion_items

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
            seen.add(resolved)
            result.append(resolved)
    return result


def select_history(configured: Path) -> Path | None:
    for candidate in history_candidates(configured):
        if probe_history(candidate).get("compatible"):
            return candidate
    return None


def _live_shell(html: str) -> str:
    shell = r'''
<style>
#lpllm-runtime-block{margin:0 0 18px}#lpllm-runtime-head{display:flex;justify-content:space-between;gap:12px;align-items:end;margin:0 0 10px}#lpllm-runtime-head h2{margin:0;font-size:17px}#lpllm-runtime-head a{font-size:12px}#lpllm-dbpath{font-family:ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere}
</style>
<script>
(()=>{
function fmt(n){if(n==null)return '—';if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KiB';return (n/1048576).toFixed(1)+' MiB';}
function install(){const first=document.querySelector('.stats');if(!first||document.getElementById('lpllm-runtime-block'))return;const block=document.createElement('section');block.id='lpllm-runtime-block';block.innerHTML=`<div id="lpllm-runtime-head"><div><div class="eyebrow">Runtime staging</div><h2>Live scanner & promotion activity</h2></div><a href="/discoveries">Review promotion pipeline →</a></div><div class="stats"><div class="stat"><div class="statlabel">Live discoveries</div><div class="statvalue" id="lpllm-active">0</div><div class="statfoot">active staged listings</div></div><div class="stat"><div class="statlabel">Held for review</div><div class="statvalue" id="lpllm-held">0</div><div class="statfoot">evidence gates not met</div></div><div class="stat"><div class="statlabel">Promotion ready</div><div class="statvalue" id="lpllm-ready">0</div><div class="statfoot">passes current gates</div></div><div class="stat"><div class="statlabel">Auto canonical</div><div class="statvalue" id="lpllm-canonical">0</div><div class="statfoot">active promoted records</div></div></div>`;first.parentNode.insertBefore(block,first);for(const el of document.querySelectorAll('.statlabel')){const t=el.textContent.trim();if(t==='Catalog records')el.textContent='Canonical catalog records';else if(t==='Priced records')el.textContent='Canonical priced records';else if(t==='Memory known')el.textContent='Canonical memory known';else if(t==='Low-risk entries')el.textContent='Canonical low-risk entries';}}
async function update(){install();try{const [r,p]=await Promise.all([fetch('/api/state',{cache:'no-store'}),fetch('/api/promotion-state?limit=1',{cache:'no-store'})]),s=await r.json(),x=await p.json();document.getElementById('lpllm-active').textContent=s.active_listings||0;document.getElementById('lpllm-held').textContent=x.counts?.held||0;document.getElementById('lpllm-ready').textContent=x.counts?.promotion_ready||0;document.getElementById('lpllm-canonical').textContent=x.counts?.canonical||0;}catch(_){}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',update);else update();setInterval(update,3000);const es=new EventSource('/api/events');es.onmessage=update;
})();
</script>
'''
    return html.replace("</body>", shell + "</body>") if "</body>" in html else html + shell


def _merge_active_promotion(live: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    projected = {
        (str(item.get("source", "")), str(item.get("source_id", ""))): item
        for item in snapshot.get("items", [])
        if isinstance(item, dict)
    }
    merged: list[dict[str, Any]] = []
    counts = {state: 0 for state in STATES}
    reason_counts: dict[str, int] = {}
    for active in live.get("items", []):
        identity = (str(active.get("source", "")), str(active.get("source_id", "")))
        detail = projected.get(identity, {})
        row = dict(active)
        for key in ("manufacturer", "sku", "mpn", "source_confidence", "sku_confidence", "canonical_id"):
            if detail.get(key) not in (None, ""):
                row[key] = detail[key]
        state = str(detail.get("promotion_state") or "discovered")
        reasons = [str(value) for value in detail.get("promotion_reasons", [])]
        row["promotion_state"] = state
        row["promotion_reasons"] = reasons
        counts[state] = counts.get(state, 0) + 1
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        merged.append(row)
    return {
        "total": len(merged),
        "sources": live.get("sources", []),
        "counts": counts,
        "reason_counts": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "promotion_report_generated_at": snapshot.get("promotion_report_generated_at"),
        "items": merged,
    }


def main() -> int:
    from . import dashboard_service as dashboard

    original_state = dashboard._history_state_sync
    original_shell = dashboard._inject_live_shell
    original_create = dashboard.create_dashboard_app

    def compatible_state(configured: Path) -> dict[str, Any]:
        configured = configured.expanduser().resolve()
        candidate = select_history(configured)
        if candidate is not None:
            state = original_state(candidate)
            state["configured_history_path"] = str(configured)
            state["history_path"] = str(candidate)
            state["auto_selected_history"] = candidate != configured
            state["schema_status"] = "live_history"
            try:
                state["database_bytes"] = candidate.stat().st_size
            except OSError:
                state["database_bytes"] = None
            if state.get("latest_run") is None:
                state["latest_run"] = {"status": "waiting_for_scanner"}
            return state
        info = probe_history(configured)
        status = "misconfigured" if info.get("database_exists") else "disconnected"
        return {"database_exists": bool(info.get("database_exists")), "database_bytes": configured.stat().st_size if configured.exists() else None, "observations": 0, "active_listings": 0, "max_observation_id": 0, "latest_run": {"status": status}, "recent": [], "scanner_status": status, "schema_status": "legacy_or_incompatible" if info.get("database_exists") else "missing", "missing_tables": info.get("missing_tables", []), "configured_history_path": str(configured), "history_path": None}

    async def discoveries_page(_: web.Request) -> web.Response:
        return web.Response(text=LIVE_DISCOVERIES_HTML, content_type="text/html", headers={"Cache-Control": "no-store"})

    async def discoveries_api(request: web.Request) -> web.Response:
        configured = Path(request.app["dashboard_history"])
        candidate = select_history(configured)
        if candidate is None:
            return web.json_response({"path": None, "total": 0, "sources": [], "items": [], "error": "live history database is not connected"}, status=503)
        try:
            limit = min(1000, max(1, int(request.query.get("limit", "200"))))
            offset = max(0, int(request.query.get("offset", "0")))
        except ValueError:
            limit, offset = 200, 0
        payload = await query_live(candidate, limit=limit, offset=offset, query=request.query.get("q", "").strip(), source=request.query.get("source", "").strip())
        return web.json_response(payload)

    async def promotion_api(request: web.Request) -> web.Response:
        configured = Path(request.app["dashboard_history"])
        candidate = select_history(configured)
        if candidate is None:
            return web.json_response({"total": 0, "sources": [], "counts": {state: 0 for state in STATES}, "reason_counts": {}, "items": [], "error": "live history database is not connected"}, status=503)
        try:
            limit = min(2000, max(1, int(request.query.get("limit", "500"))))
            offset = max(0, int(request.query.get("offset", "0")))
        except ValueError:
            limit, offset = 500, 0
        root = project_root()
        live, snapshot = await asyncio.gather(
            query_live(candidate, limit=10000, offset=0),
            asyncio.to_thread(
                build_promotion_snapshot,
                discovery_path=root / "results" / "discovery-latest.json",
                report_path=root / "results" / "promotion-latest.json",
                catalog_path=root / "data" / "catalog" / "auto-promoted.json",
            ),
        )
        merged = _merge_active_promotion(live, snapshot)
        filtered = filter_promotion_items(
            merged["items"],
            state=request.query.get("state", ""),
            reason=request.query.get("reason", ""),
            query=request.query.get("q", ""),
            source=request.query.get("source", ""),
        )
        merged["filtered_total"] = len(filtered)
        merged["items"] = filtered[offset : offset + limit]
        merged["limit"] = limit
        merged["offset"] = offset
        return web.json_response(merged)

    def create_with_live_routes(**kwargs: Any) -> web.Application:
        app = original_create(**kwargs)
        app.router.add_get("/discoveries", discoveries_page)
        app.router.add_get("/api/discoveries", discoveries_api)
        app.router.add_get("/api/promotion-state", promotion_api)
        return app

    dashboard._history_state_sync = compatible_state
    dashboard._inject_live_shell = lambda html: _live_shell(original_shell(html))
    dashboard.create_dashboard_app = create_with_live_routes
    return dashboard.main()


if __name__ == "__main__":
    raise SystemExit(main())
