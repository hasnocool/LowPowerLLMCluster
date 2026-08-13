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
        return {"path": str(path), "compatible": False, "database_exists": True, "database_error": f"{type(exc).__name__}: {exc}"}
    missing = sorted(EXPECTED_TABLES - tables)
    return {"path": str(path), "compatible": not missing, "database_exists": True, "missing_tables": missing}
