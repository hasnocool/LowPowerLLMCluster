from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web

from .catalog import load_catalog
from .dashboard import render_catalog_dashboard
from .event_log import EventJournal


DEFAULT_OUTPUT = "results/catalog-dashboard.html"
DEFAULT_HISTORY = "results/catalog-history.sqlite3"
DEFAULT_EVENTS = "results/events.jsonl"


def render_dashboard_snapshot(output: str | Path = DEFAULT_OUTPUT) -> Path:
    """Render the current canonical catalog dashboard and return the HTML path."""
    destination = Path(output).expanduser().resolve()
    catalog = load_catalog()
    parts = list(catalog.get("parts", []))
    return render_catalog_dashboard(parts, destination)


def _history_state_sync(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"database_exists": False, "observations": 0, "active_listings": 0, "max_observation_id": 0, "latest_run": None, "recent": []}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        observations, max_id = connection.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM observations").fetchone()
        active = connection.execute("SELECT COUNT(*) FROM listing_state WHERE disappeared = 0").fetchone()[0]
        latest = connection.execute("SELECT run_id, started_at, completed_at, status FROM refresh_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        recent = connection.execute("SELECT id, run_id, source, source_id, observed_at, title, price, currency FROM observations ORDER BY id DESC LIMIT 20").fetchall()
        connection.close()
        return {
            "database_exists": True,
            "observations": int(observations),
            "active_listings": int(active),
            "max_observation_id": int(max_id),
            "latest_run": dict(latest) if latest else None,
            "recent": [dict(row) for row in recent],
        }
    except sqlite3.Error as exc:
        return {"database_exists": True, "database_error": f"{type(exc).__name__}: {exc}", "observations": 0, "active_listings": 0, "max_observation_id": 0, "latest_run": None, "recent": []}


async def _history_state(path: Path) -> dict[str, Any]:
    return await asyncio.to_thread(_history_state_sync, path)


def _inject_live_shell(html: str) -> str:
    shell = r'''
<style>
#lpllm-live{position:fixed;right:16px;bottom:16px;z-index:9999;background:#111827;border:1px solid #334155;border-radius:12px;padding:9px 12px;color:#cbd5e1;font:12px/1.35 system-ui;box-shadow:0 8px 30px #0008;display:flex;gap:12px;align-items:center}#lpllm-live strong{color:#86efac}#lpllm-live a{color:#93c5fd;text-decoration:none}
</style>
<div id="lpllm-live"><strong>LIVE</strong><span id="lpllm-live-text">connecting…</span><a href="/logs">Logs</a></div>
<script>
(()=>{const text=document.getElementById('lpllm-live-text');let last=0;
async function state(){try{const r=await fetch('/api/state',{cache:'no-store'}),s=await r.json();last=s.max_observation_id||last;text.textContent=`${s.observations||0} observations · ${s.active_listings||0} active · ${s.latest_run?.status||'idle'}`;}catch(e){text.textContent='status unavailable';}}
state();setInterval(state,3000);
const es=new EventSource('/api/events');es.onmessage=(e)=>{try{const v=JSON.parse(e.data);if(v.event==='database_updated') text.textContent=`${v.observations} observations · ${v.active_listings} active · processing`;else if(v.event==='cycle_completed') text.textContent=`cycle complete · ${v.observation_count||0} processed`;else if(v.event==='cycle_error') text.textContent='scanner error — see logs';}catch(_){}};es.onerror=()=>{text.textContent='reconnecting…';};})();
</script>
'''
    return html.replace("</body>", shell + "</body>") if "</body>" in html else html + shell


_LOGS_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LowPowerLLMCluster Logs</title><style>body{margin:0;background:#090d13;color:#dbe7f5;font:14px system-ui}.top{position:sticky;top:0;background:#101722;border-bottom:1px solid #263449;padding:16px 20px;display:flex;gap:18px;align-items:center}.top a{color:#8db9ff}.status{margin-left:auto;color:#9fb0c5}.wrap{padding:18px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.card{background:#101722;border:1px solid #263449;border-radius:10px;padding:12px}.v{font-size:22px;font-weight:700;margin-top:6px}.log{background:#05080d;border:1px solid #263449;border-radius:10px;overflow:hidden}.row{display:grid;grid-template-columns:185px 170px 1fr;gap:12px;padding:8px 12px;border-bottom:1px solid #172131;font-family:ui-monospace,SFMono-Regular,monospace;font-size:12px}.row:last-child{border-bottom:0}.event{color:#8db9ff}.err{color:#ff9b9b}.ok{color:#86efac}@media(max-width:800px){.cards{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}.ts{color:#718096}}</style></head><body><div class="top"><b>Live event logs</b><a href="/">Dashboard</a><span class="status" id="connection">connecting…</span></div><div class="wrap"><div class="cards"><div class="card">Observations<div class="v" id="obs">0</div></div><div class="card">Active listings<div class="v" id="active">0</div></div><div class="card">Run status<div class="v" id="run">—</div></div><div class="card">Last DB id<div class="v" id="dbid">0</div></div></div><div id="log" class="log"></div></div><script>
const log=document.getElementById('log'),conn=document.getElementById('connection');
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function add(v){const row=document.createElement('div');row.className='row';const cls=String(v.event||'').includes('error')?'err':String(v.event||'').includes('completed')?'ok':'event';const details={...v};delete details.ts;delete details.event;row.innerHTML=`<span class="ts">${esc(v.ts||'')}</span><span class="${cls}">${esc(v.event||'event')}</span><span>${esc(JSON.stringify(details))}</span>`;log.prepend(row);while(log.children.length>500)log.removeChild(log.lastChild);}
async function state(){try{const r=await fetch('/api/state',{cache:'no-store'}),s=await r.json();obs.textContent=s.observations||0;active.textContent=s.active_listings||0;run.textContent=s.latest_run?.status||'idle';dbid.textContent=s.max_observation_id||0;}catch(_){}}
(async()=>{try{const r=await fetch('/api/logs?limit=200',{cache:'no-store'});for(const v of await r.json())add(v);}catch(_){}})();state();setInterval(state,2000);
const es=new EventSource('/api/events');es.onopen=()=>conn.textContent='live';es.onmessage=e=>{try{add(JSON.parse(e.data));state();}catch(_){}};es.onerror=()=>conn.textContent='reconnecting…';
</script></body></html>'''


async def _refresh_snapshot(app: web.Application) -> None:
    output: Path = app["dashboard_output"]
    interval = app["dashboard_refresh_interval"]
    if interval is None:
        return
    while True:
        try:
            await asyncio.to_thread(render_dashboard_snapshot, output)
            app["dashboard_last_error"] = None
        except Exception as exc:
            app["dashboard_last_error"] = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(float(interval))


async def _watch_database(app: web.Application) -> None:
    history: Path = app["dashboard_history"]
    events: EventJournal = app["dashboard_events"]
    poll_s = float(app["dashboard_db_poll"])
    previous: dict[str, Any] | None = None
    while True:
        state = await _history_state(history)
        app["dashboard_db_state"] = state
        key = (state.get("max_observation_id"), (state.get("latest_run") or {}).get("run_id"), (state.get("latest_run") or {}).get("status"))
        old_key = None if previous is None else (previous.get("max_observation_id"), (previous.get("latest_run") or {}).get("run_id"), (previous.get("latest_run") or {}).get("status"))
        if previous is not None and key != old_key:
            await events.emit("database_updated", observations=state.get("observations", 0), active_listings=state.get("active_listings", 0), max_observation_id=state.get("max_observation_id", 0), latest_run=state.get("latest_run"))
        previous = state
        await asyncio.sleep(poll_s)


async def _startup(app: web.Application) -> None:
    output: Path = app["dashboard_output"]
    await asyncio.to_thread(render_dashboard_snapshot, output)
    app["dashboard_db_state"] = await _history_state(app["dashboard_history"])
    if app["dashboard_refresh_interval"] is not None:
        app["dashboard_refresh_task"] = asyncio.create_task(_refresh_snapshot(app))
    app["dashboard_watch_task"] = asyncio.create_task(_watch_database(app))


async def _cleanup(app: web.Application) -> None:
    for name in ("dashboard_refresh_task", "dashboard_watch_task"):
        task: asyncio.Task[Any] | None = app.get(name)
        if task is None: continue
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


async def _index(request: web.Request) -> web.Response:
    output: Path = request.app["dashboard_output"]
    if not output.exists(): await asyncio.to_thread(render_dashboard_snapshot, output)
    html = await asyncio.to_thread(output.read_text, encoding="utf-8")
    return web.Response(text=_inject_live_shell(html), content_type="text/html", headers={"Cache-Control": "no-store"})


async def _logs_page(_: web.Request) -> web.Response:
    return web.Response(text=_LOGS_HTML, content_type="text/html", headers={"Cache-Control": "no-store"})


async def _state(request: web.Request) -> web.Response:
    return web.json_response(request.app.get("dashboard_db_state") or await _history_state(request.app["dashboard_history"]))


async def _logs(request: web.Request) -> web.Response:
    try: limit = min(1000, max(1, int(request.query.get("limit", "200"))))
    except ValueError: limit = 200
    return web.json_response(await request.app["dashboard_events"].tail(limit))


async def _events(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"})
    await response.prepare(request)
    journal: EventJournal = request.app["dashboard_events"]
    try:
        for payload in await journal.tail(20):
            await response.write(f"data: {json.dumps(payload, default=str)}\n\n".encode())
        async for payload in journal.follow(start_at_end=True):
            await response.write(f"data: {json.dumps(payload, default=str)}\n\n".encode())
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return response


async def _health(request: web.Request) -> web.Response:
    output: Path = request.app["dashboard_output"]
    error = request.app.get("dashboard_last_error")
    state = request.app.get("dashboard_db_state") or {}
    return web.json_response({"status": "ok" if output.exists() and error is None else "degraded", "dashboard": str(output), "snapshot_exists": output.exists(), "last_refresh_error": error, "database": state}, status=200 if output.exists() else 503)


def create_dashboard_app(*, output: str | Path = DEFAULT_OUTPUT, history: str | Path = DEFAULT_HISTORY, event_log: str | Path = DEFAULT_EVENTS, refresh_interval: float | None = None, db_poll: float = 0.5) -> web.Application:
    if refresh_interval is not None and refresh_interval <= 0: raise ValueError("refresh_interval must be positive when supplied")
    if db_poll <= 0: raise ValueError("db_poll must be positive")
    app = web.Application()
    app["dashboard_output"] = Path(output).expanduser().resolve()
    app["dashboard_history"] = Path(history).expanduser().resolve()
    app["dashboard_events"] = EventJournal(event_log)
    app["dashboard_refresh_interval"] = refresh_interval
    app["dashboard_db_poll"] = float(db_poll)
    app["dashboard_last_error"] = None
    app.router.add_get("/", _index); app.router.add_get("/index.html", _index); app.router.add_get("/logs", _logs_page)
    app.router.add_get("/api/state", _state); app.router.add_get("/api/logs", _logs); app.router.add_get("/api/events", _events); app.router.add_get("/healthz", _health)
    app.on_startup.append(_startup); app.on_cleanup.append(_cleanup)
    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the live LowPowerLLMCluster catalog dashboard")
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="static HTML snapshot path")
    parser.add_argument("--history", default=DEFAULT_HISTORY, help="SQLite discovery history watched for live updates")
    parser.add_argument("--event-log", default=DEFAULT_EVENTS, help="shared JSONL event stream written by discovery and dashboard services")
    parser.add_argument("--db-poll", type=float, default=0.5, help="seconds between lightweight database change checks")
    parser.add_argument("--refresh-interval", "--interval", dest="refresh_interval", type=float, default=None, help="optional periodic static snapshot regeneration; live status/log updates do not require it")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = create_dashboard_app(output=args.output, history=args.history, event_log=args.event_log, refresh_interval=args.refresh_interval, db_poll=args.db_poll)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__": raise SystemExit(main())
