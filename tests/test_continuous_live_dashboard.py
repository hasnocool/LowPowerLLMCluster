from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from lowpower_llm_cluster.dashboard_service import _history_state_sync, build_parser, create_dashboard_app
from lowpower_llm_cluster.event_log import EventJournal
from lowpower_llm_cluster.service_install import render_systemd_unit


def test_event_journal_round_trip(tmp_path: Path) -> None:
    async def scenario() -> None:
        journal = EventJournal(tmp_path / "events.jsonl")
        await journal.emit("cycle_started", cycle=1)
        await journal.emit("cycle_completed", cycle=1, observation_count=42)
        rows = await journal.tail(10)
        assert [row["event"] for row in rows] == ["cycle_started", "cycle_completed"]
        assert rows[-1]["observation_count"] == 42
    asyncio.run(scenario())


def test_history_state_reads_committed_batches(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE refresh_runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL);
        CREATE TABLE observations (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, source TEXT, source_id TEXT, observed_at TEXT, title TEXT, price REAL, currency TEXT);
        CREATE TABLE listing_state (source TEXT, source_id TEXT, disappeared INTEGER NOT NULL DEFAULT 0);
    """)
    db.execute("INSERT INTO refresh_runs VALUES ('run-1','2026-08-13T20:00:00Z',NULL,'running')")
    db.execute("INSERT INTO observations(run_id,source,source_id,observed_at,title,price,currency) VALUES ('run-1','vendor','sku-1','2026-08-13T20:00:01Z','One',99,'CAD')")
    db.execute("INSERT INTO listing_state VALUES ('vendor','sku-1',0)")
    db.commit(); db.close()
    state = _history_state_sync(path)
    assert state["observations"] == 1
    assert state["active_listings"] == 1
    assert state["max_observation_id"] == 1
    assert state["latest_run"]["status"] == "running"
    assert state["recent"][0]["title"] == "One"


def test_dashboard_exposes_live_routes_and_safe_default_port(tmp_path: Path) -> None:
    app = create_dashboard_app(output=tmp_path / "dashboard.html", history=tmp_path / "history.sqlite3", event_log=tmp_path / "events.jsonl")
    paths = {route.resource.canonical for route in app.router.routes()}
    assert {"/", "/logs", "/api/state", "/api/logs", "/api/events", "/healthz"} <= paths
    args = build_parser().parse_args([])
    assert args.port == 8788
    assert args.refresh_interval is None


def test_systemd_defaults_to_continuous_and_timer_is_optional() -> None:
    common = dict(service_command="llm-cluster-service", config="config.json", history="history.sqlite3", output="latest.json", cache="cache.json")
    continuous = render_systemd_unit(**common, interval=None)
    scheduled = render_systemd_unit(**common, interval=120)
    assert "--interval" not in continuous
    assert "continuous" in continuous
    assert "--interval 120" in scheduled
    assert "scheduled every 120s" in scheduled
