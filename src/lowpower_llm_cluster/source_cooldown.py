from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery import utc_now_iso
from .source_failures import cooldown_cycles

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_cooldown (
  source TEXT PRIMARY KEY,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  failure_class TEXT NOT NULL DEFAULT '',
  cooldown_until_cycle INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  last_success_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_cooldown_due ON source_cooldown(cooldown_until_cycle);
"""


class SourceCooldownStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.executescript(_SCHEMA)
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with closing(self._connect()) as connection:
            connection.commit()

    async def record_cycle(self, *, cycle_index: int, selected_sources: Sequence[str], errors: Mapping[str, str]) -> None:
        await asyncio.to_thread(self._record_cycle_sync, int(cycle_index), tuple(selected_sources), dict(errors))

    def _record_cycle_sync(self, cycle_index: int, selected_sources: Sequence[str], errors: Mapping[str, str]) -> None:
        now = utc_now_iso()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for source in selected_sources:
                    row = connection.execute("SELECT * FROM source_cooldown WHERE source=?", (source,)).fetchone()
                    previous = dict(row) if row else {}
                    error = str(errors.get(source, ""))
                    if error:
                        failures = int(previous.get("consecutive_failures", 0)) + 1
                        failure_class, cooldown = cooldown_cycles(error, failures)
                        connection.execute(
                            """INSERT INTO source_cooldown(source, consecutive_failures, failure_class, cooldown_until_cycle, last_error, last_success_at, updated_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT(source) DO UPDATE SET consecutive_failures=excluded.consecutive_failures,
                                 failure_class=excluded.failure_class, cooldown_until_cycle=excluded.cooldown_until_cycle,
                                 last_error=excluded.last_error, updated_at=excluded.updated_at""",
                            (source, failures, failure_class, cycle_index + cooldown, error[:2000], previous.get("last_success_at"), now),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO source_cooldown(source, consecutive_failures, failure_class, cooldown_until_cycle, last_error, last_success_at, updated_at)
                               VALUES (?, 0, '', 0, '', ?, ?)
                               ON CONFLICT(source) DO UPDATE SET consecutive_failures=0, failure_class='',
                                 cooldown_until_cycle=0, last_error='', last_success_at=excluded.last_success_at, updated_at=excluded.updated_at""",
                            (source, now, now),
                        )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    async def policies(self, sources: Sequence[str]) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._policies_sync, tuple(sources))

    def _policies_sync(self, sources: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not sources:
            return {}
        with closing(self._connect()) as connection:
            placeholders = ",".join("?" for _ in sources)
            rows = connection.execute(
                f"SELECT * FROM source_cooldown WHERE source IN ({placeholders})", tuple(sources)
            ).fetchall()
        return {str(row["source"]): dict(row) for row in rows}
