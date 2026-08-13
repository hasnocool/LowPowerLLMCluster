from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import AsyncIterator, Sequence
from urllib.parse import urljoin, urlparse

from .discovery import ProductObservation, _parse_jsonld_page, canonical_url
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .resilience_runtime import AdaptiveBatchSizer


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)
                return


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._title_parts: list[str] = []
        self.meta: dict[str, str] = {}

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "meta":
            return
        key = (values.get("property") or values.get("name") or "").strip().lower()
        content = values.get("content", "").strip()
        if key and content:
            self.meta.setdefault(key, content)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def extract_xml_links(text: str, mode: str) -> tuple[list[str], list[str]]:
    root = ET.fromstring(text)
    root_name = _local(root.tag)
    pages: list[str] = []
    children: list[str] = []
    if mode == "sitemap" or root_name in {"urlset", "sitemapindex"}:
        target = children if root_name == "sitemapindex" else pages
        for node in root.iter():
            if _local(node.tag) == "loc" and node.text and node.text.strip():
                target.append(node.text.strip())
        return pages, children
    for node in root.iter():
        if _local(node.tag) != "link":
            continue
        value = node.attrib.get("href") or node.text or ""
        if value.strip():
            pages.append(value.strip())
    return pages, children


def extract_html_links(base_url: str, text: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(text)
    return [urljoin(base_url, value) for value in parser.links]


def parse_page_metadata(name: str, url: str, text: str, *, discovery_kind: str) -> ProductObservation | None:
    parser = _PageMetadataParser()
    parser.feed(text)
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title
    title = " ".join(title.split())
    if not title:
        return None
    description = parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or ""
    published_at = parser.meta.get("article:published_time") or parser.meta.get("date") or parser.meta.get("datepublished") or ""
    price_raw = parser.meta.get("product:price:amount") or parser.meta.get("og:price:amount") or ""
    currency = parser.meta.get("product:price:currency") or parser.meta.get("og:price:currency") or "USD"
    try:
        price = float(price_raw.replace(",", "")) if price_raw else None
    except ValueError:
        price = None
    return ProductObservation(
        source=name,
        source_id=canonical_url(url),
        listing_url=url,
        title=title,
        price=price,
        currency=currency,
        attributes={
            "discovery_kind": discovery_kind,
            "description": " ".join(description.split())[:4000],
            "published_at": published_at,
            "metadata_fallback": True,
        },
    )


def _allowed(url: str, *, base_hosts: set[str], same_host: bool, include: Sequence[re.Pattern[str]], exclude: Sequence[re.Pattern[str]]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if same_host and parsed.netloc.lower() not in base_hosts:
        return False
    if include and not any(pattern.search(url) for pattern in include):
        return False
    if any(pattern.search(url) for pattern in exclude):
        return False
    return True


@dataclass(slots=True)
class PublicWebDiscoveryAdapter:
    """Credential-free bounded public-web discovery.

    ``html_index``/``sitemap``/``feed`` discover product pages and prefer schema.org Product.
    ``announcement_index`` records article metadata so announcement sites can seed later product enrichment.
    """

    name: str
    mode: str
    seeds: Sequence[str]
    client: AsyncHttpClient
    cache: DiscoveryCache
    adaptive: AdaptiveConcurrency
    include_patterns: Sequence[str] = ()
    exclude_patterns: Sequence[str] = ()
    same_host: bool = True
    max_candidate_pages: int = 250
    max_index_pages: int = 16
    subworkers: int = 4
    batch_size: int = 128
    batch_sizer: AdaptiveBatchSizer | None = None
    fallback_page_metadata: bool = False
    discovery_kind: str = "product_page"

    async def _fetch_text(self, url: str) -> str:
        response = await self.client.get_response(url, validators=None, source=self.name, adaptive=self.adaptive)
        return await asyncio.to_thread(response.payload.decode, "utf-8", "replace")

    async def discover_urls(self) -> list[str]:
        include = tuple(re.compile(value, re.I) for value in self.include_patterns)
        exclude = tuple(re.compile(value, re.I) for value in self.exclude_patterns)
        base_hosts = {urlparse(seed).netloc.lower() for seed in self.seeds if urlparse(seed).netloc}
        queue = list(dict.fromkeys(self.seeds))
        visited_indexes: set[str] = set()
        candidates: list[str] = []
        seen_candidates: set[str] = set()
        while queue and len(visited_indexes) < self.max_index_pages and len(candidates) < self.max_candidate_pages:
            index_url = queue.pop(0)
            if index_url in visited_indexes:
                continue
            visited_indexes.add(index_url)
            text = await self._fetch_text(index_url)
            if self.mode in {"html_index", "announcement_index"}:
                pages = await asyncio.to_thread(extract_html_links, index_url, text)
                children: list[str] = []
            else:
                pages, children = await asyncio.to_thread(extract_xml_links, text, self.mode)
            for child in children:
                parsed = urlparse(child)
                if parsed.scheme not in {"http", "https"}:
                    continue
                if self.same_host and parsed.netloc.lower() not in base_hosts:
                    continue
                if child not in visited_indexes and child not in queue and len(queue) < self.max_index_pages * 2:
                    queue.append(child)
            for page in pages:
                absolute = urljoin(index_url, page)
                if absolute in seen_candidates:
                    continue
                if not _allowed(absolute, base_hosts=base_hosts, same_host=self.same_host, include=include, exclude=exclude):
                    continue
                seen_candidates.add(absolute)
                candidates.append(absolute)
                if len(candidates) >= self.max_candidate_pages:
                    break
        return candidates

    async def _product_page(self, url: str) -> list[ProductObservation]:
        response = await self.client.get_response(url, validators=self.cache.validators(url), source=self.name, adaptive=self.adaptive)
        if response.not_modified:
            cached = self.cache.observations(url)
            if cached is not None:
                self.cache.note_hit(url)
                return list(cached)
        text = await asyncio.to_thread(response.payload.decode, "utf-8", "replace")
        records = await asyncio.to_thread(_parse_jsonld_page, self.name, url, text)
        if not records and self.fallback_page_metadata:
            fallback = await asyncio.to_thread(parse_page_metadata, self.name, url, text, discovery_kind=self.discovery_kind)
            if fallback is not None:
                records = [fallback]
        await self.cache.store(url, response, records)
        return records

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        urls = await self.discover_urls()
        if not urls:
            return
        workers = min(max(1, self.subworkers), len(urls))
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        output: asyncio.Queue[list[ProductObservation] | BaseException | None] = asyncio.Queue()
        async def producer() -> None:
            for url in urls:
                await queue.put(url)
            for _ in range(workers):
                await queue.put(None)
        async def worker() -> None:
            while True:
                url = await queue.get()
                try:
                    if url is None:
                        await output.put(None)
                        return
                    try:
                        await output.put(await self._product_page(url))
                    except BaseException as exc:
                        await output.put(exc)
                finally:
                    queue.task_done()
        failures = 0
        successful_pages = 0
        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(workers):
                group.create_task(worker())
            finished = 0
            batch: list[ProductObservation] = []
            while finished < workers:
                item = await output.get()
                if item is None:
                    finished += 1
                    continue
                if isinstance(item, BaseException):
                    failures += 1
                    continue
                successful_pages += 1
                batch.extend(item)
                target = self.batch_sizer.current if self.batch_sizer else self.batch_size
                if len(batch) >= max(1, target):
                    yield tuple(batch)
                    batch = []
            if batch:
                yield tuple(batch)
        if failures and successful_pages == 0:
            raise RuntimeError(f"all {failures} public product page fetches failed")

    async def discover(self) -> Sequence[ProductObservation]:
        records: list[ProductObservation] = []
        async for batch in self.discover_batches():
            records.extend(batch)
        return records
