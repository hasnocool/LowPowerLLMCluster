from __future__ import annotations

import sqlite3
from pathlib import Path

from lowpower_llm_cluster.history_compat import EXPECTED_TABLES, history_candidates, probe_history
from lowpower_llm_cluster.service_install import render_dashboard_systemd_unit, render_systemd_unit


def _make_live_history(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript("CREATE TABLE observations (id INTEGER PRIMARY KEY); CREATE TABLE listing_state (source TEXT, source_id TEXT, disappeared INTEGER); CREATE TABLE refresh_runs (run_id TEXT, started_at TEXT, completed_at TEXT, status TEXT);")
    connection.commit(); connection.close()


def test_probe_history_rejects_legacy_schema(tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "ingest" / "catalog.sqlite3"; legacy.parent.mkdir(parents=True)
    connection = sqlite3.connect(legacy); connection.execute("CREATE TABLE products (id INTEGER PRIMARY KEY)"); connection.commit(); connection.close()
    result = probe_history(legacy)
    assert result["database_exists"] is True and result["compatible"] is False
    assert set(result["missing_tables"]) == EXPECTED_TABLES


def test_candidates_find_new_results_history_from_old_ingest_path(tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "ingest" / "catalog.sqlite3"; live = tmp_path / "results" / "catalog-history.sqlite3"
    _make_live_history(live); candidates = history_candidates(legacy)
    assert live.resolve() in candidates and probe_history(live)["compatible"] is True


def test_scanner_and_dashboard_units_share_runtime_paths() -> None:
    history = "/srv/lpllm/results/catalog-history.sqlite3"; events = "/srv/lpllm/results/events.jsonl"
    discovery = "/srv/lpllm/results/latest.json"; report = "/srv/lpllm/results/promotion.json"
    catalog = "/srv/lpllm/data/catalog/auto.json"; health = "/srv/lpllm/results/promotion-health.json"
    scanner = render_systemd_unit(service_command="/usr/bin/llm-cluster-service", config="/srv/lpllm/config.json", history=history, output=discovery, cache="/srv/lpllm/results/cache.json", event_log=events, interval=None)
    dashboard = render_dashboard_systemd_unit(dashboard_command="/usr/bin/llm-cluster-dashboard", history=history, event_log=events, output="/srv/lpllm/results/dashboard.html", discovery_output=discovery, promotion_report=report, promotion_catalog=catalog, promotion_health=health, host="127.0.0.1", port=8788, db_poll=0.5)
    assert f"--history {history}" in scanner and f"--history {history}" in dashboard
    assert f"--event-log {events}" in scanner and f"--event-log {events}" in dashboard
    assert f"--discovery-output {discovery}" in dashboard
    assert f"--promotion-report {report}" in dashboard
    assert f"--promotion-catalog {catalog}" in dashboard
    assert f"--promotion-health {health}" in dashboard
    assert "--interval" not in scanner and "llm-cluster-dashboard" in dashboard
