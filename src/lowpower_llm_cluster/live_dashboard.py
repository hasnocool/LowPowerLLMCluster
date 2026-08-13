from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def live_product_state(path: Path, *, limit: int = 200) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"live_products": 0, "live_priced": 0, "live_stock_known": 0, "live_sources": 0, "products": []}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        live_products = connection.execute("SELECT COUNT(*) FROM listing_state WHERE disappeared = 0").fetchone()[0]
        live_priced = connection.execute("SELECT COUNT(*) FROM listing_state WHERE disappeared = 0 AND price IS NOT NULL").fetchone()[0]
        live_stock_known = connection.execute("SELECT COUNT(*) FROM listing_state WHERE disappeared = 0 AND in_stock IS NOT NULL").fetchone()[0]
        live_sources = connection.execute("SELECT COUNT(DISTINCT source) FROM listing_state WHERE disappeared = 0").fetchone()[0]
        rows = connection.execute(
            """
            SELECT ls.source, ls.source_id, ls.listing_url, ls.title, ls.price, ls.currency,
                   ls.in_stock, ls.last_seen_at, ls.missing_runs, ls.disappeared,
                   (SELECT o.payload_json FROM observations o
                    WHERE o.source = ls.source AND o.source_id = ls.source_id
                    ORDER BY o.id DESC LIMIT 1) AS payload_json
            FROM listing_state ls
            WHERE ls.disappeared = 0
            ORDER BY ls.last_seen_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 2000)),),
        ).fetchall()
        products: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload_raw = item.pop("payload_json", None)
            payload: dict[str, Any] = {}
            if payload_raw:
                try:
                    decoded = json.loads(payload_raw)
                    if isinstance(decoded, dict):
                        payload = decoded
                except (TypeError, json.JSONDecodeError):
                    pass
            item.update({
                "manufacturer": payload.get("manufacturer", ""),
                "sku": payload.get("sku", ""),
                "mpn": payload.get("mpn", ""),
                "seller": payload.get("seller", ""),
                "shipping": payload.get("shipping"),
                "attributes": payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {},
            })
            products.append(item)
        return {
            "live_products": int(live_products),
            "live_priced": int(live_priced),
            "live_stock_known": int(live_stock_known),
            "live_sources": int(live_sources),
            "products": products,
        }
    finally:
        connection.close()


def inject_live_discovery(html: str) -> str:
    shell = r'''
<style>
#lpllm-discovery{margin:0 0 18px;border:1px solid #273244;background:#11161f;border-radius:14px;overflow:hidden}
#lpllm-discovery .ld-head{padding:14px 17px;border-bottom:1px solid #273244;display:flex;align-items:center;gap:10px}
#lpllm-discovery .ld-head strong{font-size:14px}#lpllm-discovery .pulse{width:8px;height:8px;border-radius:50%;background:#65d6a6;box-shadow:0 0 0 5px rgba(101,214,166,.1)}
#lpllm-discovery .ld-head a{margin-left:auto;color:#78a9ff;text-decoration:none;font-size:12px}
#lpllm-discovery .ld-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}
#lpllm-discovery .ld-card{padding:14px 17px;border-right:1px solid #273244}.ld-card:last-child{border-right:0}.ld-label{color:#93a2b8;font-size:11px}.ld-value{font-size:24px;font-weight:760;margin-top:5px}.ld-foot{color:#6f7f95;font-size:11px;margin-top:3px}
#lpllm-discovery .ld-recent{border-top:1px solid #273244;padding:10px 17px 13px}.ld-recent-title{color:#93a2b8;font-size:11px;margin-bottom:8px}.ld-items{display:grid;gap:5px}.ld-item{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:10px;color:#edf3fb;font-size:12px}.ld-source,.ld-price{color:#93a2b8}.ld-empty{color:#93a2b8;font-size:12px}
@media(max-width:800px){#lpllm-discovery .ld-grid{grid-template-columns:1fr 1fr}.ld-card:nth-child(2){border-right:0}.ld-card:nth-child(-n+2){border-bottom:1px solid #273244}.ld-item{grid-template-columns:1fr}.ld-source,.ld-price{display:none}}
</style>
<script>
(()=>{
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function install(){
  const stats=document.querySelector('.stats'); if(!stats||document.getElementById('lpllm-discovery')) return;
  document.querySelectorAll('.statlabel').forEach(el=>{if(el.textContent.trim()==='Catalog records')el.textContent='Curated catalog records';});
  const panel=document.createElement('section'); panel.id='lpllm-discovery';
  panel.innerHTML=`<div class="ld-head"><span class="pulse"></span><strong>Live Discovery</strong><span id="ld-status" class="muted">connecting…</span><a href="/live">View all discovered products →</a></div><div class="ld-grid"><div class="ld-card"><div class="ld-label">Active discovered products</div><div class="ld-value" id="ld-products">0</div><div class="ld-foot">current listing_state rows</div></div><div class="ld-card"><div class="ld-label">Priced discoveries</div><div class="ld-value" id="ld-priced">0</div><div class="ld-foot">live listings with price</div></div><div class="ld-card"><div class="ld-label">Stock status known</div><div class="ld-value" id="ld-stock">0</div><div class="ld-foot">live listings with stock state</div></div><div class="ld-card"><div class="ld-label">Active sources</div><div class="ld-value" id="ld-sources">0</div><div class="ld-foot">sources contributing listings</div></div></div><div class="ld-recent"><div class="ld-recent-title">Newest live products</div><div id="ld-items" class="ld-items"><div class="ld-empty">No live discoveries yet.</div></div></div>`;
  stats.parentNode.insertBefore(panel,stats);
}
async function refresh(){install();try{const r=await fetch('/api/live-products?limit=6',{cache:'no-store'});const s=await r.json();document.getElementById('ld-products').textContent=s.live_products||0;document.getElementById('ld-priced').textContent=s.live_priced||0;document.getElementById('ld-stock').textContent=s.live_stock_known||0;document.getElementById('ld-sources').textContent=s.live_sources||0;document.getElementById('ld-status').textContent=`${s.latest_run?.status||'watching'} · updated ${new Date().toLocaleTimeString()}`;const box=document.getElementById('ld-items');const items=s.products||[];box.innerHTML=items.length?items.map(p=>`<div class="ld-item"><a href="${esc(p.listing_url)}" target="_blank" rel="noopener">${esc(p.title||p.source_id)}</a><span class="ld-source">${esc(p.source)}</span><span class="ld-price">${p.price==null?'—':esc(p.currency)+' '+Number(p.price).toFixed(2)}</span></div>`).join(''):'<div class="ld-empty">No live discoveries yet.</div>';}catch(e){const x=document.getElementById('ld-status');if(x)x.textContent='live data unavailable';}}
install();refresh();setInterval(refresh,2000);const es=new EventSource('/api/events');es.onmessage=()=>refresh();
})();
</script>
'''
    return html.replace("</body>", shell + "</body>") if "</body>" in html else html + shell


LIVE_PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Live Discovery · LowPowerLLMCluster</title><style>body{margin:0;background:#0a0d12;color:#edf3fb;font:14px system-ui}.top{position:sticky;top:0;background:#11161f;border-bottom:1px solid #273244;padding:14px 20px;display:flex;gap:16px;align-items:center}.top a{color:#78a9ff}.live{color:#65d6a6}.wrap{padding:18px;max-width:1600px;margin:auto}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.card,.table{background:#11161f;border:1px solid #273244;border-radius:12px}.card{padding:14px}.n{font-size:25px;font-weight:750;margin-top:5px}.table{overflow:auto}table{width:100%;border-collapse:collapse;min-width:900px}th,td{padding:10px 12px;border-bottom:1px solid #273244;text-align:left}th{color:#93a2b8;font-size:11px;position:sticky;top:49px;background:#11161f}a{color:#78a9ff;text-decoration:none}.muted{color:#93a2b8}.search{margin-bottom:12px;width:100%;max-width:560px;padding:10px 12px;background:#151c27;color:#edf3fb;border:1px solid #273244;border-radius:9px}@media(max-width:800px){.stats{grid-template-columns:1fr 1fr}}</style></head><body><div class="top"><b>Live Discovery</b><span class="live" id="conn">● LIVE</span><a href="/">Catalog dashboard</a><a href="/logs">Logs</a></div><div class="wrap"><div class="stats"><div class="card">Active products<div class="n" id="products">0</div></div><div class="card">Priced<div class="n" id="priced">0</div></div><div class="card">Stock known<div class="n" id="stock">0</div></div><div class="card">Sources<div class="n" id="sources">0</div></div></div><input id="q" class="search" placeholder="Filter title, manufacturer, SKU, source…"><div class="table"><table><thead><tr><th>Product</th><th>Source</th><th>Manufacturer / SKU</th><th>Price</th><th>Stock</th><th>Last seen</th></tr></thead><tbody id="rows"></tbody></table></div></div><script>
let all=[];const q=document.getElementById('q');function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function draw(){const needle=q.value.toLowerCase();const data=all.filter(p=>`${p.title} ${p.source} ${p.manufacturer} ${p.sku} ${p.mpn}`.toLowerCase().includes(needle));rows.innerHTML=data.map(p=>`<tr><td><a href="${esc(p.listing_url)}" target="_blank" rel="noopener">${esc(p.title||p.source_id)}</a></td><td>${esc(p.source)}</td><td>${esc([p.manufacturer,p.sku||p.mpn].filter(Boolean).join(' · ')||'—')}</td><td>${p.price==null?'—':esc(p.currency)+' '+Number(p.price).toFixed(2)}</td><td>${p.in_stock==null?'unknown':p.in_stock?'in stock':'out'}</td><td class="muted">${esc(p.last_seen_at)}</td></tr>`).join('');}q.oninput=draw;async function refresh(){try{const r=await fetch('/api/live-products?limit=1000',{cache:'no-store'}),s=await r.json();all=s.products||[];products.textContent=s.live_products||0;priced.textContent=s.live_priced||0;stock.textContent=s.live_stock_known||0;sources.textContent=s.live_sources||0;conn.textContent='● LIVE';draw();}catch(e){conn.textContent='● reconnecting';}}refresh();setInterval(refresh,2000);const es=new EventSource('/api/events');es.onmessage=refresh;es.onerror=()=>conn.textContent='● reconnecting';
</script></body></html>'''
