from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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
    result = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def main() -> int:
    from . import dashboard_service as dashboard
    original = dashboard._history_state_sync

    def compatible_state(configured: Path):
        configured = configured.expanduser().resolve()
        for candidate in history_candidates(configured):
            if probe_history(candidate).get("compatible"):
                state = original(candidate)
                state["configured_history_path"] = str(configured)
                state["history_path"] = str(candidate)
                state["auto_selected_history"] = candidate != configured
                state["schema_status"] = "live_history"
                if state.get("latest_run") is None:
                    state["latest_run"] = {"status": "waiting_for_scanner"}
                return state
        info = probe_history(configured)
        status = "misconfigured" if info.get("database_exists") else "disconnected"
        return {"database_exists": bool(info.get("database_exists")), "observations": 0, "active_listings": 0, "max_observation_id": 0, "latest_run": {"status": status}, "recent": [], "scanner_status": status, "schema_status": "legacy_or_incompatible" if info.get("database_exists") else "missing", "missing_tables": info.get("missing_tables", []), "configured_history_path": str(configured), "history_path": None}

    dashboard._history_state_sync = compatible_state
    return dashboard.main()


if __name__ == "__main__":
    raise SystemExit(main())
