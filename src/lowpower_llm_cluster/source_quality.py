from __future__ import annotations

import asyncio
import json
import math
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .discovery import utc_now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_quality (
    source TEXT PRIMARY KEY,
    cycles_seen INTEGER NOT NULL DEFAULT 0,
    successful_cycles INTEGER NOT NULL DEFAULT 0,
    error_cycles INTEGER NOT NULL DEFAULT 0,
    raw_observations INTEGER NOT NULL DEFAULT 0,
    unique_observations INTEGER NOT NULL DEFAULT 0,
    priced_observations INTEGER NOT NULL DEFAULT 0,
    spec_score_sum REAL NOT NULL DEFAULT 0,
    freshness_score_sum REAL NOT NULL DEFAULT 0,
    relevance_score_sum REAL NOT NULL DEFAULT 0,
    latency_ms_sum REAL NOT NULL DEFAULT 0,
    last_latency_ms REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    quality_score REAL NOT NULL DEFAULT 0.5,
    scan_every_cycles INTEGER NOT NULL DEFAULT 1,
    budget_multiplier REAL NOT NULL DEFAULT 1.0,
    last_success_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_quality_score ON source_quality(quality_score DESC);
"""

_LLM_RELEVANCE = re.compile(
    r"\b(?:gpu|gpgpu|cuda|rocm|npu|neural|ai\s+accelerator|accelerator|jetson|hailo|coral|tpu|"
    r"tensor|tops?|fpga|alveo|inference|llm|machine\s+learning|deep\s+learning|unified\s+memory|vram)\b",
    re.I,
)
_MEMORY = re.compile(r"\b(?:8|12|16|24|32|48|64|96|128|192|256)\s*gb\b", re.I)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _flatten_text(value: Any, *, limit: int = 8000) -> str:
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:limit]


def observation_signals(record: Mapping[str, Any]) -> tuple[bool, float, float, float]:
    """Return priced, spec-richness, freshness and LLM relevance signals in [0, 1]."""
    priced = record.get("price") not in (None, "")
    attributes = record.get("attributes") if isinstance(record.get("attributes"), Mapping) else {}
    fields = (
        record.get("manufacturer"), record.get("sku"), record.get("mpn"), record.get("in_stock"),
        record.get("seller"), attributes.get("model"), attributes.get("gtin"), attributes.get("description"),
    )
    populated = sum(1 for value in fields if value not in (None, "", [], {}))
    attribute_bonus = min(4, sum(1 for value in attributes.values() if value not in (None, "", [], {})))
    spec_richness = _clamp((populated + attribute_bonus) / 12.0)

    published = _parse_time(attributes.get("published_at") or record.get("published_at"))
    if published is None:
        freshness = 0.5
    else:
        age_days = max(0.0, (datetime.now(UTC) - published).total_seconds() / 86400.0)
        freshness = _clamp(math.exp(-age_days / 90.0))

    text = _flatten_text({"title": record.get("title", ""), "manufacturer": record.get("manufacturer", ""), "attributes": attributes})
    relevance = 0.0
    if _LLM_RELEVANCE.search(text):
        relevance += 0.75
    if _MEMORY.search(text):
        relevance += 0.25
    return bool(priced), spec_richness, freshness, _clamp(relevance)


@dataclass(slots=True)
class SourceCycleAccumulator:
    source: str
    unique_observations: int = 0
    priced_observations: int = 0
    spec_score_sum: float = 0.0
    freshness_score_sum: float = 0.0
    relevance_score_sum: float = 0.0

    def add(self, observations: Iterable[Mapping[str, Any]]) -> None:
        for record in observations:
            priced, spec, freshness, relevance = observation_signals(record)
            self.unique_observations += 1
            self.priced_observations += int(priced)
            self.spec_score_sum += spec
            self.freshness_score_sum += freshness
            self.relevance_score_sum += relevance


@dataclass(frozen=True, slots=True)
class SourceQualitySample:
    source: str
    success: bool
    raw_observations: int
    unique_observations: int
    priced_observations: int
    spec_score_sum: float
    freshness_score_sum: float
    relevance_score_sum: float
    latency_ms: float
    error: str = ""


def _policy(score: float, cycles_seen: int, *, min_cycles: int, max_scan_every: int, min_budget: float, max_budget: float) -> tuple[int, float]:
    if cycles_seen < min_cycles:
        return 1, 1.0
    if score >= 0.80:
        return 1, min(max_budget, 1.50)
    if score >= 0.65:
        return 1, min(max_budget, 1.25)
    if score >= 0.50:
        return min(max_scan_every, 2), 1.0
    if score >= 0.35:
        return min(max_scan_every, 3), max(min_budget, 0.75)
    return max(1, max_scan_every), max(min_budget, 0.50)


def _score(row: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    cycles = max(1, int(row["cycles_seen"]))
    unique = max(0, int(row["unique_observations"]))
    raw = max(unique, int(row["raw_observations"]))
    success_rate = _clamp(int(row["successful_cycles"]) / cycles)
    unique_yield = _clamp((unique / cycles) / 24.0)
    pricing = _clamp(int(row["priced_observations"]) / max(1, unique))
    specs = _clamp(float(row["spec_score_sum"]) / max(1, unique))
    freshness = _clamp(float(row["freshness_score_sum"]) / max(1, unique))
    relevance = _clamp(float(row["relevance_score_sum"]) / max(1, unique))
    duplicate_rate = _clamp(1.0 - (unique / max(1, raw)))
    avg_latency = float(row["latency_ms_sum"]) / cycles
    latency = _clamp(1.0 / (1.0 + avg_latency / 3000.0))
    score = (
        0.18 * success_rate + 0.12 * unique_yield + 0.12 * pricing + 0.18 * specs +
        0.10 * freshness + 0.12 * relevance + 0.08 * (1.0 - duplicate_rate) + 0.10 * latency
    )
    signals = {
        "success_rate": success_rate,
        "unique_yield": unique_yield,
        "pricing_completeness": pricing,
        "spec_richness": specs,
        "freshness": freshness,
        "llm_relevance": relevance,
        "duplicate_rate": duplicate_rate,
        "latency_score": latency,
        "avg_latency_ms": avg_latency,
    }
    return _clamp(score), signals


class SourceQualityStore:
    def __init__(
        self,
        path: str | Path,
        *,
        min_cycles_before_adaptation: int = 3,
        max_scan_every_cycles: int = 4,
        min_budget_multiplier: float = 0.5,
        max_budget_multiplier: float = 1.5,
    ) -> None:
        self.path = Path(path)
        self.min_cycles = max(1, int(min_cycles_before_adaptation))
        self.max_scan_every = max(1, int(max_scan_every_cycles))
        self.min_budget = max(0.1, float(min_budget_multiplier))
        self.max_budget = max(self.min_budget, float(max_budget_multiplier))

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

    async def record(self, samples: Sequence[SourceQualitySample]) -> list[dict[str, Any]]:
        if not samples:
            return []
        return await asyncio.to_thread(self._record_sync, tuple(samples))

    def _record_sync(self, samples: Sequence[SourceQualitySample]) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for sample in samples:
                    existing = connection.execute("SELECT * FROM source_quality WHERE source=?", (sample.source,)).fetchone()
                    if existing is None:
                        state = {
                            "source": sample.source, "cycles_seen": 0, "successful_cycles": 0, "error_cycles": 0,
                            "raw_observations": 0, "unique_observations": 0, "priced_observations": 0,
                            "spec_score_sum": 0.0, "freshness_score_sum": 0.0, "relevance_score_sum": 0.0,
                            "latency_ms_sum": 0.0, "last_latency_ms": 0.0, "last_error": "",
                        }
                    else:
                        state = dict(existing)
                    state["cycles_seen"] = int(state["cycles_seen"]) + 1
                    state["successful_cycles"] = int(state["successful_cycles"]) + int(sample.success)
                    state["error_cycles"] = int(state["error_cycles"]) + int(not sample.success)
                    state["raw_observations"] = int(state["raw_observations"]) + max(0, sample.raw_observations)
                    state["unique_observations"] = int(state["unique_observations"]) + max(0, sample.unique_observations)
                    state["priced_observations"] = int(state["priced_observations"]) + max(0, sample.priced_observations)
                    state["spec_score_sum"] = float(state["spec_score_sum"]) + sample.spec_score_sum
                    state["freshness_score_sum"] = float(state["freshness_score_sum"]) + sample.freshness_score_sum
                    state["relevance_score_sum"] = float(state["relevance_score_sum"]) + sample.relevance_score_sum
                    state["latency_ms_sum"] = float(state["latency_ms_sum"]) + max(0.0, sample.latency_ms)
                    state["last_latency_ms"] = max(0.0, sample.latency_ms)
                    state["last_error"] = sample.error[:2000]
                    score, signals = _score(state)
                    scan_every, budget = _policy(
                        score, int(state["cycles_seen"]), min_cycles=self.min_cycles,
                        max_scan_every=self.max_scan_every, min_budget=self.min_budget, max_budget=self.max_budget,
                    )
                    now = utc_now_iso()
                    connection.execute(
                        """INSERT INTO source_quality(
                               source, cycles_seen, successful_cycles, error_cycles, raw_observations,
                               unique_observations, priced_observations, spec_score_sum, freshness_score_sum,
                               relevance_score_sum, latency_ms_sum, last_latency_ms, last_error, quality_score,
                               scan_every_cycles, budget_multiplier, last_success_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(source) DO UPDATE SET
                               cycles_seen=excluded.cycles_seen, successful_cycles=excluded.successful_cycles,
                               error_cycles=excluded.error_cycles, raw_observations=excluded.raw_observations,
                               unique_observations=excluded.unique_observations, priced_observations=excluded.priced_observations,
                               spec_score_sum=excluded.spec_score_sum, freshness_score_sum=excluded.freshness_score_sum,
                               relevance_score_sum=excluded.relevance_score_sum, latency_ms_sum=excluded.latency_ms_sum,
                               last_latency_ms=excluded.last_latency_ms, last_error=excluded.last_error,
                               quality_score=excluded.quality_score, scan_every_cycles=excluded.scan_every_cycles,
                               budget_multiplier=excluded.budget_multiplier,
                               last_success_at=COALESCE(excluded.last_success_at, source_quality.last_success_at),
                               updated_at=excluded.updated_at""",
                        (
                            sample.source, state["cycles_seen"], state["successful_cycles"], state["error_cycles"],
                            state["raw_observations"], state["unique_observations"], state["priced_observations"],
                            state["spec_score_sum"], state["freshness_score_sum"], state["relevance_score_sum"],
                            state["latency_ms_sum"], state["last_latency_ms"], state["last_error"], score,
                            scan_every, budget, now if sample.success else None, now,
                        ),
                    )
                    updated.append({"source": sample.source, "quality_score": score, "scan_every_cycles": scan_every, "budget_multiplier": budget, **signals})
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return updated

    async def policies(self, sources: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
        names = tuple(sorted(set(sources or ())))
        return await asyncio.to_thread(self._policies_sync, names)

    def _policies_sync(self, names: Sequence[str]) -> dict[str, dict[str, Any]]:
        with closing(self._connect()) as connection:
            if names:
                placeholders = ",".join("?" for _ in names)
                rows = connection.execute(
                    f"SELECT source, quality_score, scan_every_cycles, budget_multiplier, cycles_seen FROM source_quality WHERE source IN ({placeholders})",
                    names,
                ).fetchall()
            else:
                rows = connection.execute("SELECT source, quality_score, scan_every_cycles, budget_multiplier, cycles_seen FROM source_quality").fetchall()
        return {str(row["source"]): dict(row) for row in rows}

    async def snapshot(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._snapshot_sync, max(1, int(limit)))

    def _snapshot_sync(self, limit: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM source_quality ORDER BY quality_score DESC, source LIMIT ?", (limit,)).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            _, signals = _score(item)
            item["signals"] = signals
            values.append(item)
        return values
