from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Mapping

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


def _payload_without_observed_at(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    payload.pop("observed_at", None)
    return payload


def _decode_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


class CompactingCatalogHistory(CatalogHistory):
    """Keep state fresh while compacting only truly unchanged observations."""

    def __init__(self, path, *, unchanged_heartbeat_s: float = 3600.0) -> None:
        super().__init__(path)
        self.unchanged_heartbeat_s = max(60.0, float(unchanged_heartbeat_s))
        self.compacted_observations = 0

    def _record_batch_sync(self, run_id, observations):
        connection = self._ensure_connection_sync()
        previous_seen: dict[tuple[str, str], str | None] = {}
        previous_payloads: dict[tuple[str, str], dict[str, Any]] = {}
        for item in observations:
            row = connection.execute(
                "SELECT observed_at, payload_json FROM observations WHERE source=? AND source_id=? ORDER BY id DESC LIMIT 1",
                (item.source, item.source_id),
            ).fetchone()
            identity = (item.source, item.source_id)
            previous_seen[identity] = None if row is None else str(row[0])
            previous_payloads[identity] = {} if row is None else _decode_payload(row[1])

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

            prior_payload = _payload_without_observed_at(previous_payloads.get(identity))
            current_payload = _payload_without_observed_at(asdict(item))
            if prior_payload != current_payload:
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
