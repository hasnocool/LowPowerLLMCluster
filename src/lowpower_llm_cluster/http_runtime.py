from __future__ import annotations

import asyncio
import gzip
import json
import os
import random
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

import aiohttp

from .discovery import ProductObservation, canonical_url


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    payload: bytes
    headers: Mapping[str, str]
    attempts: int
    elapsed_ms: float
    not_modified: bool = False


@dataclass(frozen=True, slots=True)
class CachedPage:
    etag: str = ""
    last_modified: str = ""
    body_bytes: int = 0
    observations: tuple[ProductObservation, ...] = ()
    stored_at: float = 0.0
    last_accessed: float = 0.0


def _cache_bytes(entries: Mapping[str, CachedPage]) -> bytes:
    payload = {
        "version": 2,
        "entries": {
            url: {
                "etag": entry.etag,
                "last_modified": entry.last_modified,
                "body_bytes": entry.body_bytes,
                "stored_at": entry.stored_at,
                "last_accessed": entry.last_accessed,
                "observations": [asdict(item) for item in entry.observations],
            }
            for url, entry in entries.items()
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_cache_atomic(path: Path, entries: Mapping[str, CachedPage], compress: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = _cache_bytes(entries)
    if compress:
        payload = gzip.compress(payload, compresslevel=6)
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _read_cache(path: Path, compress: bool) -> dict[str, Any]:
    raw = path.read_bytes()
    if compress or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


class DiscoveryCache:
    """Persistent conditional cache with TTL, LRU-style pruning and optional gzip storage."""

    def __init__(self, path: Path | str, entries: Mapping[str, CachedPage] | None = None, *, max_observations_per_entry: int = 5000, ttl_s: float = 7 * 24 * 3600, max_entries: int = 10000, compress: bool = False) -> None:
        if ttl_s <= 0 or max_entries < 1:
            raise ValueError("cache ttl/max entries must be positive")
        self.path = Path(path)
        self._entries = dict(entries or {})
        self.max_observations_per_entry = max(1, int(max_observations_per_entry))
        self.ttl_s = float(ttl_s)
        self.max_entries = int(max_entries)
        self.compress = bool(compress)
        self._dirty = False
        self._hits = self._bytes_saved = self._expired = self._evicted = self._prunes = 0

    @classmethod
    async def open(cls, path: Path | str, *, max_observations_per_entry: int = 5000, ttl_s: float = 7 * 24 * 3600, max_entries: int = 10000, compress: bool = False) -> "DiscoveryCache":
        path = Path(path)
        if not await asyncio.to_thread(path.exists):
            return cls(path, max_observations_per_entry=max_observations_per_entry, ttl_s=ttl_s, max_entries=max_entries, compress=compress)
        try:
            payload = await asyncio.to_thread(_read_cache, path, compress)
        except (OSError, ValueError, json.JSONDecodeError, gzip.BadGzipFile):
            return cls(path, max_observations_per_entry=max_observations_per_entry, ttl_s=ttl_s, max_entries=max_entries, compress=compress)
        now = time.time()
        entries: dict[str, CachedPage] = {}
        for url, item in payload.get("entries", {}).items():
            observations = tuple(ProductObservation(**obs) for obs in item.get("observations", ()))
            stored_at = float(item.get("stored_at", now))
            entries[url] = CachedPage(
                etag=str(item.get("etag", "")), last_modified=str(item.get("last_modified", "")),
                body_bytes=int(item.get("body_bytes", 0)), observations=observations,
                stored_at=stored_at, last_accessed=float(item.get("last_accessed", stored_at)),
            )
        cache = cls(path, entries, max_observations_per_entry=max_observations_per_entry, ttl_s=ttl_s, max_entries=max_entries, compress=compress)
        cache.prune(now=now)
        return cache

    def _fresh(self, key: str, *, now: float | None = None) -> CachedPage | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = time.time() if now is None else now
        if entry.stored_at and now - entry.stored_at > self.ttl_s:
            del self._entries[key]
            self._expired += 1
            self._dirty = True
            return None
        touched = CachedPage(entry.etag, entry.last_modified, entry.body_bytes, entry.observations, entry.stored_at, now)
        self._entries[key] = touched
        self._dirty = True
        return touched

    def validators(self, url: str) -> dict[str, str]:
        entry = self._fresh(canonical_url(url))
        if entry is None or not entry.observations:
            return {}
        headers: dict[str, str] = {}
        if entry.etag:
            headers["If-None-Match"] = entry.etag
        if entry.last_modified:
            headers["If-Modified-Since"] = entry.last_modified
        return headers

    def observations(self, url: str) -> tuple[ProductObservation, ...] | None:
        entry = self._fresh(canonical_url(url))
        return None if entry is None else entry.observations

    def note_hit(self, url: str) -> None:
        entry = self._fresh(canonical_url(url))
        self._hits += 1
        self._bytes_saved += 0 if entry is None else entry.body_bytes

    def prune(self, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        before = len(self._entries)
        expired = [key for key, entry in self._entries.items() if entry.stored_at and now - entry.stored_at > self.ttl_s]
        for key in expired:
            del self._entries[key]
        self._expired += len(expired)
        over = max(0, len(self._entries) - self.max_entries)
        if over:
            oldest = sorted(self._entries.items(), key=lambda pair: pair[1].last_accessed or pair[1].stored_at)[:over]
            for key, _ in oldest:
                del self._entries[key]
            self._evicted += len(oldest)
        removed = before - len(self._entries)
        if removed:
            self._dirty = True
        self._prunes += 1
        return removed

    def metrics(self) -> dict[str, int | float | bool]:
        return {
            "entries": len(self._entries),
            "cacheable_entries": sum(1 for entry in self._entries.values() if entry.observations),
            "not_modified_hits": self._hits, "estimated_bytes_saved": self._bytes_saved,
            "expired_entries": self._expired, "evicted_entries": self._evicted, "prune_runs": self._prunes,
            "ttl_s": self.ttl_s, "max_entries": self.max_entries, "compressed": self.compress,
        }

    async def store(self, url: str, response: HttpResponse, observations: Sequence[ProductObservation]) -> None:
        serialized = tuple(observations)
        if len(serialized) > self.max_observations_per_entry:
            serialized = ()
        now = time.time()
        self._entries[canonical_url(url)] = CachedPage(
            etag=str(response.headers.get("etag", "")), last_modified=str(response.headers.get("last-modified", "")),
            body_bytes=len(response.payload), observations=serialized, stored_at=now, last_accessed=now,
        )
        self._dirty = True
        if len(self._entries) > self.max_entries:
            self.prune(now=now)

    async def flush(self) -> None:
        self.prune()
        if self._dirty:
            await asyncio.to_thread(_write_cache_atomic, self.path, dict(self._entries), self.compress)
            self._dirty = False


class AdaptiveConcurrency:
    """AIMD-like source limiter: fast backoff, cautious recovery."""

    def __init__(self, *, minimum: int, maximum: int, initial: int | None = None, success_window: int = 8, latency_target_ms: float = 1500.0, enabled: bool = True) -> None:
        if minimum < 1 or maximum < minimum or success_window < 1 or latency_target_ms <= 0:
            raise ValueError("invalid adaptive concurrency bounds")
        self.minimum = minimum
        self.maximum = maximum
        self.current = max(minimum, min(maximum, initial or maximum))
        self.success_window = success_window
        self.latency_target_ms = latency_target_ms
        self.enabled = enabled
        self._condition = asyncio.Condition()
        self._in_flight = self._success_streak = 0
        self._ewma_ms: float | None = None
        self._decreases = self._increases = self._rate_limits = self._errors = 0

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._condition:
            await self._condition.wait_for(lambda: self._in_flight < self.current)
            self._in_flight += 1
        try:
            yield
        finally:
            async with self._condition:
                self._in_flight -= 1
                self._condition.notify_all()

    async def observe(self, *, latency_ms: float, success: bool, rate_limited: bool = False) -> None:
        if not self.enabled:
            return
        async with self._condition:
            alpha = 0.2
            self._ewma_ms = latency_ms if self._ewma_ms is None else alpha * latency_ms + (1 - alpha) * self._ewma_ms
            if not success or rate_limited:
                self._success_streak = 0
                self._rate_limits += int(rate_limited)
                self._errors += int(not rate_limited)
                reduced = max(self.minimum, max(1, self.current // 2))
                if reduced < self.current:
                    self.current = reduced
                    self._decreases += 1
                    self._condition.notify_all()
                return
            self._success_streak += 1
            if self._success_streak >= self.success_window and self.current < self.maximum and (self._ewma_ms or 0) <= self.latency_target_ms:
                self.current += 1
                self._success_streak = 0
                self._increases += 1
                self._condition.notify_all()

    def metrics(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "minimum": self.minimum, "maximum": self.maximum, "current": self.current, "ewma_latency_ms": None if self._ewma_ms is None else round(self._ewma_ms, 3), "increases": self._increases, "decreases": self._decreases, "rate_limits": self._rate_limits, "errors": self._errors}


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


class _RetryableHttpStatus(RuntimeError):
    pass


@asynccontextmanager
async def _null_slot() -> AsyncIterator[None]:
    yield


class AsyncHttpClient:
    RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(self, *, concurrency: int = 16, per_host: int = 4, timeout_s: float = 20.0, max_response_bytes: int = 8 * 1024 * 1024, retry_attempts: int = 3, retry_backoff_base_s: float = 0.5, retry_backoff_max_s: float = 15.0, retry_jitter_s: float = 0.25, user_agent: str = "LowPowerLLMCluster/0.5") -> None:
        if concurrency < 1 or per_host < 1 or per_host > concurrency:
            raise ValueError("HTTP concurrency must be positive and per_host <= concurrency")
        if timeout_s <= 0 or max_response_bytes < 1 or retry_attempts < 1:
            raise ValueError("timeout/response size/retry_attempts must be positive")
        if min(retry_backoff_base_s, retry_backoff_max_s, retry_jitter_s) < 0:
            raise ValueError("retry backoff/jitter cannot be negative")
        self.concurrency = concurrency
        self.per_host = per_host
        self.timeout_s = timeout_s
        self.max_response_bytes = max_response_bytes
        self.retry_attempts = retry_attempts
        self.retry_backoff_base_s = retry_backoff_base_s
        self.retry_backoff_max_s = retry_backoff_max_s
        self.retry_jitter_s = retry_jitter_s
        self.user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None
        self._gate = asyncio.BoundedSemaphore(concurrency)
        self._in_flight = self._max_in_flight = self._requests = self._attempts = 0
        self._bytes = self._retries = self._rate_limits = self._conditional_requests = self._not_modified = 0
        self._retry_sleep_s = 0.0
        self._source_metrics: dict[str, dict[str, float | int]] = {}

    async def __aenter__(self) -> "AsyncHttpClient":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is not None and not self._session.closed:
            return
        connector = aiohttp.TCPConnector(limit=self.concurrency, limit_per_host=self.per_host, ttl_dns_cache=600, keepalive_timeout=60.0)
        timeout = aiohttp.ClientTimeout(total=self.timeout_s, connect=min(self.timeout_s, 10.0))
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers={"User-Agent": self.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}, auto_decompress=True)

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and not session.closed:
            await session.close()

    def _bucket(self, source: str) -> dict[str, float | int]:
        return self._source_metrics.setdefault(source or "unknown", {"attempts": 0, "retries": 0, "rate_limits": 0, "bytes": 0, "not_modified": 0, "latency_ms": 0.0})

    def metrics(self) -> dict[str, Any]:
        return {"requests": self._requests, "attempts": self._attempts, "retries": self._retries, "rate_limits": self._rate_limits, "conditional_requests": self._conditional_requests, "not_modified": self._not_modified, "bytes": self._bytes, "retry_sleep_s": round(self._retry_sleep_s, 3), "max_in_flight": self._max_in_flight, "connection_limit": self.concurrency, "per_host_limit": self.per_host, "sources": {key: dict(value) for key, value in self._source_metrics.items()}}

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(self.retry_backoff_max_s, retry_after)
        base = min(self.retry_backoff_max_s, self.retry_backoff_base_s * (2 ** max(0, attempt - 1)))
        return max(0.0, base + random.uniform(0.0, self.retry_jitter_s))

    async def get_response(self, url: str, *, validators: Mapping[str, str] | None = None, source: str = "", adaptive: AdaptiveConcurrency | None = None) -> HttpResponse:
        if self._session is None or self._session.closed:
            await self.start()
        assert self._session is not None
        headers = dict(validators or {})
        self._requests += 1
        self._conditional_requests += int(bool(headers))
        bucket = self._bucket(source)
        for attempt in range(1, self.retry_attempts + 1):
            started = time.perf_counter()
            retry_after = None
            rate_limited = False
            self._attempts += 1
            bucket["attempts"] = int(bucket["attempts"]) + 1
            try:
                async with (adaptive.slot() if adaptive else _null_slot()):
                    async with self._gate:
                        self._in_flight += 1
                        self._max_in_flight = max(self._max_in_flight, self._in_flight)
                        try:
                            async with self._session.get(url, headers=headers) as response:
                                response_headers = {key.lower(): value for key, value in response.headers.items()}
                                if response.status == 304:
                                    elapsed = (time.perf_counter() - started) * 1000
                                    self._not_modified += 1
                                    bucket["not_modified"] = int(bucket["not_modified"]) + 1
                                    if adaptive:
                                        await adaptive.observe(latency_ms=elapsed, success=True)
                                    return HttpResponse(304, b"", response_headers, attempt, round(elapsed, 3), True)
                                if response.status in self.RETRYABLE_STATUSES:
                                    rate_limited = response.status == 429
                                    if rate_limited:
                                        self._rate_limits += 1
                                        bucket["rate_limits"] = int(bucket["rate_limits"]) + 1
                                    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                                    if attempt < self.retry_attempts:
                                        await response.read()
                                        raise _RetryableHttpStatus(str(response.status))
                                response.raise_for_status()
                                payload = bytearray()
                                async for chunk in response.content.iter_chunked(64 * 1024):
                                    payload.extend(chunk)
                                    if len(payload) > self.max_response_bytes:
                                        raise ValueError(f"response from {url!r} exceeded {self.max_response_bytes} bytes")
                                elapsed = (time.perf_counter() - started) * 1000
                                self._bytes += len(payload)
                                bucket["bytes"] = int(bucket["bytes"]) + len(payload)
                                bucket["latency_ms"] = float(bucket["latency_ms"]) + elapsed
                                if adaptive:
                                    await adaptive.observe(latency_ms=elapsed, success=True)
                                return HttpResponse(response.status, bytes(payload), response_headers, attempt, round(elapsed, 3))
                        finally:
                            self._in_flight -= 1
            except (_RetryableHttpStatus, aiohttp.ClientError, asyncio.TimeoutError):
                elapsed = (time.perf_counter() - started) * 1000
                if adaptive:
                    await adaptive.observe(latency_ms=elapsed, success=False, rate_limited=rate_limited)
                if attempt >= self.retry_attempts:
                    raise
                delay = self._backoff(attempt, retry_after)
                self._retries += 1
                bucket["retries"] = int(bucket["retries"]) + 1
                self._retry_sleep_s += delay
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable retry state")

    async def iter_json_items(self, url: str, *, prefix: str, source: str = "", adaptive: AdaptiveConcurrency | None = None) -> AsyncIterator[Any]:
        """Stream a JSON array with ijson; retry only before the first yielded item."""
        if self._session is None or self._session.closed:
            await self.start()
        assert self._session is not None
        bucket = self._bucket(source)
        self._requests += 1
        yielded = False
        for attempt in range(1, self.retry_attempts + 1):
            started = time.perf_counter()
            rate_limited = False
            retry_after = None
            self._attempts += 1
            bucket["attempts"] = int(bucket["attempts"]) + 1
            try:
                async with (adaptive.slot() if adaptive else _null_slot()):
                    async with self._gate:
                        self._in_flight += 1
                        self._max_in_flight = max(self._max_in_flight, self._in_flight)
                        try:
                            async with self._session.get(url) as response:
                                if response.status in self.RETRYABLE_STATUSES:
                                    rate_limited = response.status == 429
                                    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                                    if rate_limited:
                                        self._rate_limits += 1
                                        bucket["rate_limits"] = int(bucket["rate_limits"]) + 1
                                    if attempt < self.retry_attempts:
                                        await response.read()
                                        raise _RetryableHttpStatus(str(response.status))
                                response.raise_for_status()
                                try:
                                    import ijson
                                except ImportError as exc:
                                    raise RuntimeError("streaming JSON feeds require the ijson package") from exc
                                before = getattr(response.content, "total_bytes", 0)
                                async for item in ijson.items_async(response.content, prefix):
                                    yielded = True
                                    yield item
                                transferred = max(0, getattr(response.content, "total_bytes", before) - before)
                                self._bytes += transferred
                                bucket["bytes"] = int(bucket["bytes"]) + transferred
                                elapsed = (time.perf_counter() - started) * 1000
                                bucket["latency_ms"] = float(bucket["latency_ms"]) + elapsed
                                if adaptive:
                                    await adaptive.observe(latency_ms=elapsed, success=True)
                                return
                        finally:
                            self._in_flight -= 1
            except (_RetryableHttpStatus, aiohttp.ClientError, asyncio.TimeoutError):
                elapsed = (time.perf_counter() - started) * 1000
                if adaptive:
                    await adaptive.observe(latency_ms=elapsed, success=False, rate_limited=rate_limited)
                if yielded or attempt >= self.retry_attempts:
                    raise
                delay = self._backoff(attempt, retry_after)
                self._retries += 1
                bucket["retries"] = int(bucket["retries"]) + 1
                self._retry_sleep_s += delay
                await asyncio.sleep(delay)
