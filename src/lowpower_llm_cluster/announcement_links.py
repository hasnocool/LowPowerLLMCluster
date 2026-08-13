from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Sequence
from urllib.parse import urlparse

from .discovery import ProductObservation, canonical_url
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient
from .public_discovery import extract_html_links

_IGNORED_HOST_SUFFIXES = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "youtube.com", "youtu.be",
    "instagram.com", "pinterest.com", "reddit.com", "google.com", "doubleclick.net",
)
_IGNORED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp4")


def _host(url: str) -> str:
    value = (urlparse(url).hostname or "").lower().rstrip(".")
    return value[4:] if value.startswith("www.") else value


def _ignored(host: str) -> bool:
    return not host or any(host == suffix or host.endswith("." + suffix) for suffix in _IGNORED_HOST_SUFFIXES)


def extract_vendor_links(article_url: str, html: str, *, limit: int = 12) -> list[str]:
    article_host = _host(article_url)
    values: list[str] = []
    seen: set[str] = set()
    for raw in extract_html_links(article_url, html):
        url = canonical_url(raw)
        parsed = urlparse(url)
        host = _host(url)
        if parsed.scheme not in {"http", "https"} or host == article_host or _ignored(host):
            continue
        if parsed.path.lower().endswith(_IGNORED_EXTENSIONS) or url in seen:
            continue
        seen.add(url)
        values.append(url)
        if len(values) >= max(1, int(limit)):
            break
    return values


async def hydrate_announcement_links(
    announcements: Sequence[ProductObservation],
    *,
    client: AsyncHttpClient,
    adaptive: AdaptiveConcurrency,
    max_announcements: int = 20,
    max_links_per_announcement: int = 12,
    workers: int = 2,
) -> tuple[ProductObservation, ...]:
    selected = list(announcements[: max(1, int(max_announcements))])
    if not selected:
        return ()
    queue: asyncio.Queue[tuple[int, ProductObservation] | None] = asyncio.Queue()
    output: list[ProductObservation | None] = [None] * len(selected)
    worker_count = min(max(1, int(workers)), len(selected))

    async def producer() -> None:
        for index, item in enumerate(selected):
            await queue.put((index, item))
        for _ in range(worker_count):
            await queue.put(None)

    async def worker() -> None:
        while True:
            value = await queue.get()
            try:
                if value is None:
                    return
                index, item = value
                try:
                    response = await client.get_response(
                        item.listing_url, validators=None, source="auto-source-announcement", adaptive=adaptive
                    )
                    html = await asyncio.to_thread(response.payload.decode, "utf-8", "replace")
                    links = await asyncio.to_thread(
                        extract_vendor_links, item.listing_url, html, limit=max_links_per_announcement
                    )
                except Exception:
                    links = []
                attributes = dict(item.attributes)
                attributes["outbound_links"] = links
                output[index] = replace(item, attributes=attributes)
            finally:
                queue.task_done()

    async with asyncio.TaskGroup() as group:
        group.create_task(producer())
        for _ in range(worker_count):
            group.create_task(worker())
    return tuple(item for item in output if item is not None)
