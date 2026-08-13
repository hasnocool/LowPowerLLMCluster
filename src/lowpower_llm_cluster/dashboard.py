# src/lowpower_llm_cluster/dashboard.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import midpoint_price
from .evidence import verified_memory_gb
from .reports import published_power_boundary
from .scoring import catalog_score


def _rows(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for part in parts:
        power, scope = published_power_boundary(part)
        output.append({
            "id": part.get("id"), "name": part.get("name"), "category": part.get("category"),
            "hardware_class": part.get("hardware_class", ""), "price": midpoint_price(part),
            "memory": verified_memory_gb(part), "power": power, "power_scope": scope,
            "score": catalog_score(part), "risk": part.get("risk_level", ""),
            "lifecycle": part.get("lifecycle_status", ""), "url": part.get("url", ""),
        })
    return output


def render_catalog_dashboard(parts: list[dict[str, Any]], output: Path | str) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_rows(parts), separators=(",", ":")).replace("</", "<\\/")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LowPowerLLMCluster Catalog</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}}header{{padding:1rem 1.5rem;position:sticky;top:0;background:#191919;border-bottom:1px solid #333}}main{{padding:1rem 1.5rem}}.filters{{display:flex;gap:.6rem;flex-wrap:wrap}}input,select,button{{background:#222;color:#eee;border:1px solid #444;border-radius:.4rem;padding:.55rem}}table{{width:100%;border-collapse:collapse;margin-top:1rem}}th,td{{padding:.55rem;border-bottom:1px solid #333;text-align:left}}th{{position:sticky;top:84px;background:#181818}}a{{color:#8ecbff}}.muted{{color:#aaa}}#compare{{margin-top:1rem;padding:1rem;border:1px solid #333;border-radius:.6rem;display:none}}@media(max-width:800px){{.optional{{display:none}}}}
</style></head><body><header><strong>LowPowerLLMCluster Catalog</strong><div class="filters">
<input id="q" placeholder="search"><input id="budget" type="number" placeholder="max USD"><input id="memory" type="number" placeholder="min GB"><input id="power" type="number" placeholder="max W boundary">
<select id="risk"><option value="">all risks</option><option>low</option><option>medium</option><option>high</option></select><button id="save">Save filters</button><button id="clear">Reset</button></div></header>
<main><div class="muted">Power is shown with its evidence scope; processor TDP/cTDP is never presented as complete-node wall power.</div><div id="compare"></div>
<table><thead><tr><th>Compare</th><th>Score</th><th>Product</th><th>Price</th><th>Memory</th><th>Power</th><th class="optional">Risk</th><th class="optional">Lifecycle</th></tr></thead><tbody id="rows"></tbody></table></main>
<script>const data={payload};const $=id=>document.getElementById(id);const ids=['q','budget','memory','power','risk'];let compared=new Set();
function fmt(v,s=''){{return v==null?'?':v.toLocaleString(undefined,{{maximumFractionDigits:2}})+s}}function filters(){{return Object.fromEntries(ids.map(id=>[id,$(id).value]))}}function save(){{localStorage.setItem('lpllm-filters',JSON.stringify(filters()))}}function restore(){{try{{let x=JSON.parse(localStorage.getItem('lpllm-filters')||'{{}}');ids.forEach(id=>$(id).value=x[id]||'')}}catch(e){{}}}}
function renderCompare(){{let box=$('compare'),items=data.filter(x=>compared.has(x.id));box.style.display=items.length?'block':'none';box.innerHTML=items.length?'<strong>Comparison</strong><br>'+items.map(x=>`${{x.name}} — $${{fmt(x.price)}} / ${{fmt(x.memory,' GB')}} / ${{fmt(x.power,' W')}} (${{x.power_scope}})`).join('<br>'):''}}
function render(){{let f=filters(),q=f.q.toLowerCase();let rows=data.filter(x=>(!q||(x.name+' '+x.category+' '+x.hardware_class).toLowerCase().includes(q))&&(!f.budget||(x.price!=null&&x.price<=+f.budget))&&(!f.memory||(x.memory!=null&&x.memory>=+f.memory))&&(!f.power||(x.power!=null&&x.power<=+f.power))&&(!f.risk||x.risk===f.risk));rows.sort((a,b)=>b.score-a.score);$('rows').innerHTML=rows.map(x=>`<tr><td><input type=checkbox data-id="${{x.id}}" ${{compared.has(x.id)?'checked':''}}></td><td>${{x.score.toFixed(2)}}</td><td><a href="${{x.url}}">${{x.name}}</a><div class=muted>${{x.hardware_class}}</div></td><td>$${{fmt(x.price)}}</td><td>${{fmt(x.memory,' GB')}}</td><td>${{fmt(x.power,' W')}}<div class=muted>${{x.power_scope}}</div></td><td class=optional>${{x.risk}}</td><td class=optional>${{x.lifecycle}}</td></tr>`).join('');document.querySelectorAll('[data-id]').forEach(el=>el.onchange=()=>{{el.checked?compared.add(el.dataset.id):compared.delete(el.dataset.id);renderCompare()}});renderCompare()}}
ids.forEach(id=>$(id).oninput=render);$('save').onclick=save;$('clear').onclick=()=>{{ids.forEach(id=>$(id).value='');localStorage.removeItem('lpllm-filters');render()}};restore();render();</script></body></html>"""
    output.write_text(document, encoding="utf-8")
    return output
