# src/lowpower_llm_cluster/discovery.py
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

import aiohttp


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical_url(url: str) -> str:
    """Normalize a listing URL for stable identity without inventing a SKU."""
    parsed = urlsplit(url.strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


@dataclass(frozen=True, slots=True)
class ProductObservation:
    source: str
    source_id: str
    listing_url: str
    title: str
    price: float | None = None
    currency: str = "USD"
    shipping: float | None = None
    seller: str = ""
    seller_rating: float | None = None
    seller_review_count: int | None = None
    seller_verified: bool | None = None
    manufacturer: str = ""
    sku: str = ""
    mpn: str = ""
    in_stock: bool | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=utc_now_iso)

    @property
    def identity(self) -> tuple[str, str]:
        stable_id = self.source_id.strip() or canonical_url(self.listing_url)
        return self.source.strip().lower(), stable_id


class SourceAdapter(Protocol):
    name: str

    async def discover(self) -> Sequence[ProductObservation]: ...


@dataclass(slots=True)
class StaticSourceAdapter:
    name: str
    observations: Sequence[ProductObservation]

    async def discover(self) -> Sequence[ProductObservation]:
        return list(self.observations)


class AsyncHttpClient:
    """Connection-pooled native asyncio HTTP client with bounded response sizes."""

    def __init__(
        self,
        *,
        concurrency: int = 16,
        per_host: int = 4,
        timeout_s: float = 20.0,
        max_response_bytes: int = 8 * 1024 * 1024,
        user_agent: str = "LowPowerLLMCluster/0.5",
    ) -> None:
        if concurrency < 1 or per_host < 1:
            raise ValueError("HTTP concurrency must be >= 1")
        if per_host > concurrency:
            raise ValueError("per_host cannot exceed concurrency")
        if timeout_s <= 0 or max_response_bytes < 1:
            raise ValueError("timeout_s and max_response_bytes must be positive")
        self.concurrency = concurrency
        self.per_host = per_host
        self.timeout_s = timeout_s
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None
        self._gate = asyncio.BoundedSemaphore(concurrency)
        self._in_flight = 0
        self._max_in_flight = 0
        self._requests = 0
        self._bytes = 0

    async def __aenter__(self) -> "AsyncHttpClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is not None and not self._session.closed:
            return
        connector = aiohttp.TCPConnector(
            limit=self.concurrency,
            limit_per_host=self.per_host,
            ttl_dns_cache=300,
            keepalive_timeout=30.0,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_s, connect=min(self.timeout_s, 10.0))
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            },
            auto_decompress=True,
        )

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and not session.closed:
            await session.close()

    def metrics(self) -> dict[str, int]:
        return {
            "requests": self._requests,
            "bytes": self._bytes,
            "max_in_flight": self._max_in_flight,
            "connection_limit": self.concurrency,
            "per_host_limit": self.per_host,
        }

    async def get_bytes(self, url: str) -> bytes:
        if self._session is None or self._session.closed:
            await self.start()
        assert self._session is not None
        async with self._gate:
            self._requests += 1
            self._in_flight += 1
            self._max_in_flight = max(self._max_in_flight, self._in_flight)
            try:
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    payload = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        payload.extend(chunk)
                        if len(payload) > self.max_response_bytes:
                            raise ValueError(
                                f"response from {url!r} exceeded {self.max_response_bytes} bytes"
                            )
                    self._bytes += len(payload)
                    return bytes(payload)
            finally:
                self._in_flight -= 1

    async def get_text(self, url: str) -> str:
        payload = await self.get_bytes(url)
        return await asyncio.to_thread(payload.decode, "utf-8", "replace")

    async def get_json(self, url: str) -> Any:
        text = await self.get_text(url)
        return await asyncio.to_thread(json.loads, text)


JsonParser = Callable[[Any], Iterable[ProductObservation]]


@dataclass(slots=True)
class JsonFeedAdapter:
    name: str
    endpoint: str
    parser: JsonParser
    client: AsyncHttpClient

    async def discover(self) -> Sequence[ProductObservation]:
        payload = await self.client.get_json(self.endpoint)
        return await asyncio.to_thread(lambda: list(self.parser(payload)))


class _JsonLdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._collecting = False
        self._buffer: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("type", "").lower() == "application/ld+json":
            self._collecting = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._collecting:
            self.blocks.append("".join(self._buffer))
            self._collecting = False
            self._buffer = []


def _iter_jsonld_products(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld_products(item)
        return
    if not isinstance(value, dict):
        return
    type_value = value.get("@type")
    if type_value == "Product" or (isinstance(type_value, list) and "Product" in type_value):
        yield value
    graph = value.get("@graph")
    if graph is not None:
        yield from _iter_jsonld_products(graph)


def _offer(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    return value if isinstance(value, dict) else {}


def _parse_jsonld_page(name: str, url: str, text: str) -> list[ProductObservation]:
    collector = _JsonLdCollector()
    collector.feed(text)
    observations: list[ProductObservation] = []
    for block in collector.blocks:
        try:
            decoded = json.loads(block)
        except json.JSONDecodeError:
            continue
        for product in _iter_jsonld_products(decoded):
            offer = _offer(product.get("offers"))
            brand = product.get("brand")
            manufacturer = product.get("manufacturer")
            if isinstance(brand, dict):
                brand = brand.get("name", "")
            if isinstance(manufacturer, dict):
                manufacturer = manufacturer.get("name", "")
            availability = str(offer.get("availability", "")).lower()
            in_stock = None if not availability else "instock" in availability and "outofstock" not in availability
            price = offer.get("price") or offer.get("lowPrice")
            seller = offer.get("seller")
            observations.append(
                ProductObservation(
                    source=name,
                    source_id=str(product.get("sku") or product.get("mpn") or product.get("productID") or canonical_url(url)),
                    listing_url=str(offer.get("url") or product.get("url") or url),
                    title=str(product.get("name") or "Unnamed product"),
                    price=float(price) if price not in (None, "") else None,
                    currency=str(offer.get("priceCurrency") or "USD"),
                    seller=str(seller.get("name", "")) if isinstance(seller, dict) else "",
                    manufacturer=str(manufacturer or brand or ""),
                    sku=str(product.get("sku") or ""),
                    mpn=str(product.get("mpn") or ""),
                    in_stock=in_stock,
                    attributes={
                        "model": product.get("model"),
                        "description": product.get("description"),
                        "gtin": product.get("gtin") or product.get("gtin13") or product.get("gtin14"),
                    },
                )
            )
    return observations


@dataclass(slots=True)
class JsonLdProductAdapter:
    """Schema.org page adapter with bounded per-source URL subworkers."""

    name: str
    urls: Sequence[str]
    client: AsyncHttpClient
    subworkers: int = 4
    queue_size: int = 64

    async def _discover_url(self, url: str) -> list[ProductObservation]:
        text = await self.client.get_text(url)
        return await asyncio.to_thread(_parse_jsonld_page, self.name, url, text)

    async def discover(self) -> Sequence[ProductObservation]:
        if self.subworkers < 1 or self.queue_size < 1:
            raise ValueError("subworkers and queue_size must be >= 1")
        queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue(maxsize=self.queue_size)
        results: list[list[ProductObservation]] = [[] for _ in self.urls]

        async def worker() -> None:
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        return
                    index, url = item
                    results[index] = await self._discover_url(url)
                finally:
                    queue.task_done()

        worker_count = min(self.subworkers, max(1, len(self.urls)))

        async def bounded_producer() -> None:
            for index, url in enumerate(self.urls):
                await queue.put((index, url))
            for _ in range(worker_count):
                await queue.put(None)

        async with asyncio.TaskGroup() as group:
            group.create_task(bounded_producer())
            for _ in range(worker_count):
                group.create_task(worker())

        return [item for group in results for item in group]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    observations: tuple[ProductObservation, ...]
    errors: Mapping[str, str]
    metrics: Mapping[str, Any] = field(default_factory=dict)


class DiscoveryPipeline:
    """Hierarchical agent pool: adapter agents, then adapter-specific subworkers."""

    def __init__(self, adapters: Sequence[SourceAdapter], *, worker_count: int = 4, queue_size: int = 64) -> None:
        if worker_count < 1 or queue_size < 1:
            raise ValueError("worker_count and queue_size must be >= 1")
        self.adapters = tuple(adapters)
        self.worker_count = worker_count
        self.queue_size = queue_size

    async def run(self) -> DiscoveryResult:
        started = time.perf_counter()
        queue: asyncio.Queue[SourceAdapter | None] = asyncio.Queue(maxsize=self.queue_size)
        results: dict[str, Sequence[ProductObservation]] = {}
        errors: dict[str, str] = {}
        durations_ms: dict[str, float] = {}
        result_lock = asyncio.Lock()

        worker_count = min(self.worker_count, max(1, len(self.adapters)))

        async def producer() -> None:
            for adapter in self.adapters:
                await queue.put(adapter)
            for _ in range(worker_count):
                await queue.put(None)

        async def agent() -> None:
            while True:
                adapter = await queue.get()
                try:
                    if adapter is None:
                        return
                    source_started = time.perf_counter()
                    try:
                        discovered = await adapter.discover()
                    except Exception as exc:  # one source outage must not cancel the refresh
                        async with result_lock:
                            errors[adapter.name] = f"{type(exc).__name__}: {exc}"
                    else:
                        async with result_lock:
                            results[adapter.name] = discovered
                    finally:
                        async with result_lock:
                            durations_ms[adapter.name] = round((time.perf_counter() - source_started) * 1000.0, 3)
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(worker_count):
                group.create_task(agent())

        deduped: dict[tuple[str, str], ProductObservation] = {}
        for adapter in self.adapters:
            for item in results.get(adapter.name, ()):
                deduped[item.identity] = item
        ordered = tuple(sorted(deduped.values(), key=lambda item: item.identity))
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return DiscoveryResult(
            observations=ordered,
            errors=errors,
            metrics={
                "agent_workers": self.worker_count,
                "source_count": len(self.adapters),
                "sources_succeeded": len(results),
                "sources_failed": len(errors),
                "elapsed_ms": elapsed_ms,
                "source_durations_ms": durations_ms,
            },
        )
