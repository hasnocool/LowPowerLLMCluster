from __future__ import annotations
import asyncio, sqlite3
from pathlib import Path
from lowpower_llm_cluster.history_compat import probe_history, select_history
from lowpower_llm_cluster.live_discoveries import LIVE_DISCOVERIES_HTML, query_live

def make_history(path: Path) -> None:
    con=sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE refresh_runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL);
    CREATE TABLE observations (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, source TEXT NOT NULL, source_id TEXT NOT NULL, observed_at TEXT NOT NULL, listing_url TEXT NOT NULL, title TEXT NOT NULL, price REAL, currency TEXT NOT NULL, shipping REAL, in_stock INTEGER, payload_json TEXT NOT NULL);
    CREATE TABLE listing_state (source TEXT NOT NULL, source_id TEXT NOT NULL, listing_url TEXT NOT NULL, title TEXT NOT NULL, price REAL, currency TEXT NOT NULL, in_stock INTEGER, last_seen_at TEXT NOT NULL, missing_runs INTEGER NOT NULL DEFAULT 0, disappeared INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(source, source_id));
    """)
    con.execute("INSERT INTO refresh_runs VALUES ('run1','2026-08-13T20:00:00Z',NULL,'running')")
    con.execute("INSERT INTO listing_state VALUES ('shop','sku1','https://example.test/1','New accelerator',199.0,'CAD',1,'2026-08-13T20:00:01Z',0,0)")
    con.execute("INSERT INTO listing_state VALUES ('shop','sku2','https://example.test/2','Old listing',50.0,'CAD',0,'2026-08-13T19:00:00Z',2,1)")
    con.execute("INSERT INTO observations(run_id,source,source_id,observed_at,listing_url,title,price,currency,shipping,in_stock,payload_json) VALUES ('run1','shop','sku1','2026-08-13T20:00:01Z','https://example.test/1','New accelerator',199.0,'CAD',NULL,1,'{}')")
    con.commit(); con.close()

def test_live_query_returns_active_staged_listings(tmp_path: Path) -> None:
    path=tmp_path/'catalog-history.sqlite3'; make_history(path)
    data=asyncio.run(query_live(path))
    assert data['total']==1 and data['items'][0]['title']=='New accelerator'
    assert data['items'][0]['in_stock'] is True and data['sources']==['shop']

def test_live_query_supports_search(tmp_path: Path) -> None:
    path=tmp_path/'catalog-history.sqlite3'; make_history(path)
    assert asyncio.run(query_live(path, query='accelerator'))['total']==1
    assert asyncio.run(query_live(path, query='missing'))['total']==0

def test_history_selection_finds_runtime_db(tmp_path: Path) -> None:
    legacy=tmp_path/'data'/'ingest'/'catalog.sqlite3'; legacy.parent.mkdir(parents=True); sqlite3.connect(legacy).close()
    live=tmp_path/'results'/'catalog-history.sqlite3'; live.parent.mkdir(parents=True); make_history(live)
    assert probe_history(legacy)['compatible'] is False
    assert select_history(legacy)==live.resolve()

def test_live_page_exposes_promotion_review() -> None:
    assert 'Promotion Review' in LIVE_DISCOVERIES_HTML
    assert 'Discovery → Held → Promotion Ready → Canonical' in LIVE_DISCOVERIES_HTML
    assert '/api/promotion-state' in LIVE_DISCOVERIES_HTML
