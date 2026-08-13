from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any


def _query_live_sync(path: Path, *, limit: int = 200, offset: int = 0, query: str = "", source: str = "") -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "total": 0, "sources": [], "items": []}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    where = ["disappeared = 0"]
    params: list[Any] = []
    if query:
        where.append("(title LIKE ? OR source_id LIKE ? OR listing_url LIKE ?)")
        term = f"%{query}%"
        params.extend([term, term, term])
    if source:
        where.append("source = ?")
        params.append(source)
    clause = " AND ".join(where)
    total = int(connection.execute(f"SELECT COUNT(*) FROM listing_state WHERE {clause}", params).fetchone()[0])
    sources = [str(row[0]) for row in connection.execute("SELECT DISTINCT source FROM listing_state WHERE disappeared = 0 ORDER BY source").fetchall()]
    rows = connection.execute(
        f"""SELECT source, source_id, listing_url, title, price, currency, in_stock,
                   last_seen_at, missing_runs, disappeared
            FROM listing_state WHERE {clause}
            ORDER BY last_seen_at DESC, source, source_id
            LIMIT ? OFFSET ?""",
        [*params, int(limit), int(offset)],
    ).fetchall()
    connection.close()
    items = []
    for row in rows:
        item = dict(row)
        item["in_stock"] = None if item["in_stock"] is None else bool(item["in_stock"])
        item["disappeared"] = bool(item["disappeared"])
        items.append(item)
    return {"path": str(path), "total": total, "sources": sources, "items": items, "limit": limit, "offset": offset}


async def query_live(path: Path, *, limit: int = 200, offset: int = 0, query: str = "", source: str = "") -> dict[str, Any]:
    return await asyncio.to_thread(_query_live_sync, path, limit=limit, offset=offset, query=query, source=source)


LIVE_DISCOVERIES_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Live Discoveries · LowPowerLLMCluster</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#090d13;color:#e5edf7;font:14px system-ui}.top{position:sticky;top:0;z-index:5;background:#101722;border-bottom:1px solid #263449;padding:14px 18px;display:flex;gap:16px;align-items:center}.top a{color:#8db9ff}.live{margin-left:auto;color:#86efac}.wrap{padding:18px;max-width:1600px;margin:auto}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.card{background:#101722;border:1px solid #263449;border-radius:10px;padding:12px}.v{font-size:23px;font-weight:750;margin-top:5px}.muted{color:#94a3b8}.toolbar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}.toolbar input,.toolbar select{background:#101722;color:#e5edf7;border:1px solid #334155;border-radius:8px;padding:9px}.toolbar input{min-width:280px;flex:1}.table{border:1px solid #263449;border-radius:10px;overflow:auto;background:#101722}table{border-collapse:collapse;width:100%;min-width:900px}th,td{padding:10px 12px;border-bottom:1px solid #1d2939;text-align:left}th{position:sticky;top:0;background:#121b28;color:#9fb0c5;font-size:11px;text-transform:uppercase;letter-spacing:.06em}a{color:#8db9ff;text-decoration:none}.price{font-variant-numeric:tabular-nums}.stock{color:#86efac}.out{color:#fca5a5}.path{font-family:ui-monospace,monospace;font-size:11px;overflow-wrap:anywhere}.notice{background:#132033;border:1px solid #29476a;border-radius:10px;padding:12px;margin-bottom:12px}.empty{padding:30px;text-align:center;color:#94a3b8}@media(max-width:800px){.cards{grid-template-columns:1fr 1fr}.toolbar input{min-width:100%}}</style></head><body><div class='top'><b>Live Discoveries</b><a href='/'>Canonical catalog</a><a href='/logs'>Logs</a><span id='conn' class='live'>connecting…</span></div><div class='wrap'><div class='notice'>These are live/staging listings committed by the scanner. They are persisted in SQLite immediately, but are not promoted into the verified canonical catalog until enrichment/validation accepts them.</div><div class='cards'><div class='card'>Active discoveries<div class='v' id='active'>0</div></div><div class='card'>Observations saved<div class='v' id='obs'>0</div></div><div class='card'>Scanner status<div class='v' id='status'>—</div></div><div class='card'>History DB<div class='v' id='dbsize'>—</div><div class='muted path' id='dbpath'></div></div></div><div class='toolbar'><input id='q' placeholder='Search live title, source id, or URL'><select id='source'><option value=''>All sources</option></select></div><div class='table'><table><thead><tr><th>Last seen</th><th>Source</th><th>Listing</th><th>Price</th><th>Stock</th><th>Source ID</th></tr></thead><tbody id='rows'></tbody></table><div id='empty' class='empty' hidden>No live discoveries yet.</div></div></div><script>const rows=document.getElementById('rows'),empty=document.getElementById('empty'),q=document.getElementById('q'),source=document.getElementById('source');let timer;function esc(v){return String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}async function state(){try{const r=await fetch('/api/state',{cache:'no-store'}),s=await r.json();active.textContent=s.active_listings||0;obs.textContent=s.observations||0;status.textContent=s.latest_run?.status||s.scanner_status||'unknown';dbpath.textContent=s.history_path||s.configured_history_path||'not connected';dbsize.textContent=s.database_bytes==null?'—':fmt(s.database_bytes);conn.textContent='live';}catch(_){conn.textContent='disconnected';}}function fmt(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KiB';return (n/1048576).toFixed(1)+' MiB';}async function load(){const p=new URLSearchParams({limit:'500',q:q.value,source:source.value});const r=await fetch('/api/discoveries?'+p,{cache:'no-store'}),d=await r.json();if(source.options.length===1)for(const s of d.sources||[]){const o=document.createElement('option');o.value=s;o.textContent=s;source.appendChild(o);}rows.innerHTML='';for(const v of d.items||[]){const tr=document.createElement('tr');const price=v.price==null?'—':Number(v.price).toFixed(2)+' '+esc(v.currency||'');const stock=v.in_stock==null?'unknown':v.in_stock?'in stock':'out';tr.innerHTML='<td>'+esc(v.last_seen_at)+'</td><td>'+esc(v.source)+'</td><td><a target=\"_blank\" rel=\"noopener\" href=\"'+esc(v.listing_url)+'\">'+esc(v.title)+'</a></td><td class=\"price\">'+price+'</td><td class=\"'+(v.in_stock===false?'out':'stock')+'\">'+stock+'</td><td>'+esc(v.source_id)+'</td>';rows.appendChild(tr);}empty.hidden=(d.items||[]).length>0;}function refresh(){state();load();}q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)});source.addEventListener('change',load);refresh();setInterval(refresh,3000);const es=new EventSource('/api/events');es.onopen=()=>conn.textContent='live';es.onmessage=()=>refresh();es.onerror=()=>conn.textContent='reconnecting…';</script></body></html>"""
