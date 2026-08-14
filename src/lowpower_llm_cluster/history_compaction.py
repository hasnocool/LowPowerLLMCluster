from __future__ import annotations

from datetime import UTC, datetime

from .history import CatalogHistory, ListingChange


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class CompactingCatalogHistory(CatalogHistory):
    """Keep state fresh without persisting every unchanged poll forever."""

    def __init__(self, path, *, unchanged_heartbeat_s: float = 3600.0) -> None:
        super().__init__(path)
        self.unchanged_heartbeat_s = max(60.0, float(unchanged_heartbeat_s))
        self.compacted_observations = 0

    def _record_batch_sync(self, run_id, observations):
        connection = self._ensure_connection_sync()
        previous_seen: dict[tuple[str, str], str | None] = {}
        for item in observations:
            row = connection.execute(
                "SELECT observed_at FROM observations WHERE source=? AND source_id=? ORDER BY id DESC LIMIT 1",
                (item.source, item.source_id),
            ).fetchone()
            previous_seen[(item.source, item.source_id)] = None if row is None else str(row[0])

        changes: tuple[ListingChange, ...] = super()._record_batch_sync(run_id, observations)
        changed = {(item.source, item.source_id) for item in changes}
        removable: list[tuple[str, str, str]] = []
        for item in observations:
            identity = (item.source, item.source_id)
            if identity in changed:
                continue
            previous = _parse(previous_seen.get(identity))
            current = _parse(item.observed_at)
            if previous is None or current is None:
                continue
            if (current - previous).total_seconds() < self.unchanged_heartbeat_s:
                removable.append((run_id, item.source, item.source_id))
        if removable:
            connection.executemany(
                "DELETE FROM observations WHERE run_id=? AND source=? AND source_id=?",
                removable,
            )
            connection.commit()
            self.compacted_observations += len(removable)
        return changes
