# src/lowpower_llm_cluster/discovery.py
from __future__ import annotations

import asyncio
import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit


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
    """Adapter useful for fixtures, exports, and sources discovered by another process."""

    name: str
    observations: Sequence[ProductObservation]

    async def discover(self) -> Sequence[ProductObservation]:
        await asyncio.sleep(0)
        return list(self.observations)


class AsyncHttpClient:
    """Tiny dependency-free async HTTP client.

    urllib is blocking, so each request is moved to a worker thread. No connection or
    mutable response object is shared between threads. The semaphore bounds network
    and worker pressure so discovery cannot flood a low-power host.
    """

    def __init__(self, *, concurrency: int = 4, timeout_s: float = 20.0, user_agent: str = "LowPowerLLMCluster/0.5") -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._gate = asyncio.BoundedSemaphore(concurrency)
        self.timeout_s = timeout_s
        self.user_agent = user_agent

    def _get_sync(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - URL is adapter-controlled
            return response.read()

    async def get_bytes(self, url: str) -> bytes:
        async with self._gate:
            return await asyncio.to_thread(self._get_sync, url)

    async def get_text(self, url: str) -> str:
        payload = await self.get_bytes(url)
        return payload.decode("utf-8", errors="replace")

    async def get_json(self, url: str) -> Any:
        return json.loads(await self.get_text(url))


JsonParser = Callable[[Any], Iterable[ProductObservation]]


@dataclass(slots=True)
class JsonFeedAdapter:
    """Generic adapter for vendor/reseller JSON feeds without source-specific blocking I/O."""

    name: str
    endpoint: str
    parser: JsonParser
    client: AsyncHttpClient

    async def discover(self) -> Sequence[ProductObservation]:
        payload = await self.client.get_json(self.endpoint)
        return list(self.parser(payload))


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
    if value.get("@type") == "Product" or (isinstance(value.get("@type"), list) and "Product" in value["@type"]):
        yield value
    graph = value.get("@graph")
    if graph is not None:
        yield from _iter_jsonld_products(graph)


def _offer(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class JsonLdProductAdapter:
    """Discover schema.org Product records from manufacturer/reseller product pages."""

    name: str
    urls: Sequence[str]
    client: AsyncHttpClient

    async def _discover_url(self, url: str) -> list[ProductObservation]:
        collector = _JsonLdCollector()
        collector.feed(await self.client.get_text(url))
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
                observations.append(ProductObservation(
                    source=self.name,
                    source_id=str(product.get("sku") or product.get("mpn") or product.get("productID") or canonical_url(url)),
                    listing_url=str(offer.get("url") or product.get("url") or url),
                    title=str(product.get("name") or "Unnamed product"),
                    price=float(price) if price not in (None, "") else None,
                    currency=str(offer.get("priceCurrency") or "USD"),
                    seller=str((_offer(offer.get("seller"))).get("name", "")) if isinstance(offer.get("seller"), dict) else "",
                    manufacturer=str(manufacturer or brand or ""),
                    sku=str(product.get("sku") or ""),
                    mpn=str(product.get("mpn") or ""),
                    in_stock=in_stock,
                    attributes={
                        "model": product.get("model"),
                        "description": product.get("description"),
                        "gtin": product.get("gtin") or product.get("gtin13") or product.get("gtin14"),
                    },
                ))
        return observations

    async def discover(self) -> Sequence[ProductObservation]:
        results: list[ProductObservation] = []
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._discover_url(url)) for url in self.urls]
        for task in tasks:
            results.extend(task.result())
        return results


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    observations: tuple[ProductObservation, ...]
    errors: Mapping[str, str]


class DiscoveryPipeline:
    def __init__(self, adapters: Sequence[SourceAdapter]) -> None:
        self.adapters = tuple(adapters)

    async def run(self) -> DiscoveryResult:
        results: dict[str, Sequence[ProductObservation]] = {}
        errors: dict[str, str] = {}

        async def collect(adapter: SourceAdapter) -> None:
            try:
                results[adapter.name] = await adapter.discover()
            except Exception as exc:  # keep one source outage from killing the refresh
                errors[adapter.name] = f"{type(exc).__name__}: {exc}"

        async with asyncio.TaskGroup() as group:
            for adapter in self.adapters:
                group.create_task(collect(adapter))

        deduped: dict[tuple[str, str], ProductObservation] = {}
        for adapter in self.adapters:
            for item in results.get(adapter.name, ()):
                deduped[item.identity] = item
        ordered = tuple(sorted(deduped.values(), key=lambda item: item.identity))
        return DiscoveryResult(observations=ordered, errors=errors)
