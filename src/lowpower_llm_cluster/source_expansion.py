from __future__ import annotations

import asyncio
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

from .discovery import ProductObservation, _parse_jsonld_page, canonical_url
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient
from .public_discovery import extract_html_links, extract_xml_links

_PRODUCT_PATH = re.compile(
    r"/(?:products?|shop|store|catalog|hardware|boards?|modules?|systems?|computers?|"
    r"accelerators?|edge-ai|jetson|fpga|sbc|som)(?:/|$)",
    re.I,
)
_CATEGORY_PATH = re.compile(
    r"/(?:products?|shop|store|catalog|hardware|boards?|modules?|systems?|computers?|"
    r"accelerators?|edge-ai|jetson|fpga)(?:/|$)",
    re.I,
)
_IGNORED_HOSTS = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "youtube.com",
    "youtu.be", "instagram.com", "pinterest.com", "reddit.com", "google.com",
    "googleusercontent.com", "doubleclick.net", "amazon-adsystem.com",
)
_IGNORED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip",
    ".tar", ".gz", ".7z", ".mp4", ".mp3",
)


def _host(url: str) -> str:
    value = (urlparse(url).hostname or "").lower().rstrip(".")
    return value[4:] if value.startswith("www.") else value


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), "", "", "", "")).rstrip("/")


def _ignored_host(host: str) -> bool:
    return not host or any(host == value or host.endswith("." + value) for value in _IGNORED_HOSTS)


def dynamic_source_name(source_type: str, source_url: str) -> str:
    host = re.sub(r"[^a-z0-9]+", "-", _host(source_url)).strip("-") or "unknown"
    digest = hashlib.sha1(f"{source_type}|{canonical_url(source_url)}".encode()).hexdigest()[:10]
    return f"auto-{host}-{source_type}-{digest}"


class _SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.alternates: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        rel = values.get("rel", "").lower()
        media_type = values.get("type", "").lower()
        href = values.get("href", "").strip()
        if "alternate" in rel and href and media_type in {
            "application/rss+xml", "application/atom+xml", "application/feed+json"
        }:
            self.alternates.append((media_type, href))


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    domain: str
    source_url: str
    source_type: str
    discovered_from: str
    score: float
    status: str
    active: bool
    metadata: Mapping[str, Any]

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    def as_source_config(self, *, max_candidate_pages: int = 24, subworkers: int = 2) -> dict[str, Any] | None:
        if not self.active or self.status != "verified":
            return None
        name = dynamic_source_name(self.source_type, self.source_url)
        if self.source_type == "jsonld":
            return {"name": name, "type": "jsonld", "source_trust": 0.92, "subworkers": subworkers, "urls": [self.source_url]}
        escaped_host = re.escape(urlparse(self.source_url).netloc)
        product_pattern = rf"^https://{escaped_host}/.+"
        common = {
            "name": name,
            "source_trust": 0.86,
            "subworkers": subworkers,
            "seeds": [self.source_url],
            "include_patterns": [product_pattern],
            "same_host": True,
            "max_candidate_pages": max_candidate_pages,
            "fallback_page_metadata": True,
        }
        if self.source_type == "sitemap":
            return {**common, "type": "sitemap", "source_trust": 0.9, "exclude_patterns": [r"/(?:blog|news|press|support|docs?|download|login|cart|account)(?:/|$)"], "max_index_pages": 4, "batch_size": min(24, max_candidate_pages), "discovery_kind": "auto_manufacturer_product"}
        if self.source_type == "feed":
            return {**common, "type": "feed", "source_trust": 0.76, "max_index_pages": 1, "max_candidate_pages": min(max_candidate_pages, 20), "batch_size": min(20, max_candidate_pages), "discovery_kind": "vendor_release"}
        if self.source_type == "html_index":
            return {**common, "type": "html_index", "exclude_patterns": [r"/(?:blog|news|press|support|docs?|download|login|cart|account)(?:/|$)"], "max_index_pages": 1, "batch_size": min(24, max_candidate_pages), "discovery_kind": "auto_manufacturer_product"}
        return None


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    products: tuple[ProductObservation, ...]
    candidates: tuple[SourceCandidate, ...]
    domains_considered: int
    domains_probed: int
    pages_probed: int
    errors: Mapping[str, str]


def candidate_from_record(record: Mapping[str, Any]) -> SourceCandidate:
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    return SourceCandidate(
        domain=str(record.get("domain", "")), source_url=str(record.get("source_url", "")),
        source_type=str(record.get("source_type", "")), discovered_from=str(record.get("discovered_from", "")),
        score=float(record.get("score", 0.0)), status=str(record.get("status", "candidate")),
        active=bool(record.get("active", False)), metadata=dict(metadata),
    )


def source_config_from_record(record: Mapping[str, Any], *, max_candidate_pages: int = 24, subworkers: int = 2) -> dict[str, Any] | None:
    return candidate_from_record(record).as_source_config(max_candidate_pages=max_candidate_pages, subworkers=subworkers)


class AutoSourceExpander:
    """Bounded announcement -> manufacturer source discovery."""

    def __init__(self, *, client: AsyncHttpClient, adaptive: AdaptiveConcurrency, max_announcements: int = 20, max_links_per_announcement: int = 8, max_domains_per_cycle: int = 8, max_surface_probes_per_domain: int = 8, max_products_per_cycle: int = 32) -> None:
        self.client = client
        self.adaptive = adaptive
        self.max_announcements = max(1, int(max_announcements))
        self.max_links_per_announcement = max(1, int(max_links_per_announcement))
        self.max_domains_per_cycle = max(1, int(max_domains_per_cycle))
        self.max_surface_probes_per_domain = max(1, int(max_surface_probes_per_domain))
        self.max_products_per_cycle = max(1, int(max_products_per_cycle))
        self._pages_probed = 0
        self._errors: dict[str, str] = {}

    async def _text(self, url: str, *, source: str) -> str:
        self._pages_probed += 1
        response = await self.client.get_response(url, validators=None, source=source, adaptive=self.adaptive)
        return await asyncio.to_thread(response.payload.decode, "utf-8", "replace")

    def _announcement_links(self, announcement: ProductObservation) -> list[str]:
        raw = announcement.attributes.get("outbound_links", ())
        if not isinstance(raw, (list, tuple)):
            return []
        article_host = _host(announcement.listing_url)
        links: list[str] = []
        seen: set[str] = set()
        for value in raw:
            url = canonical_url(str(value))
            parsed = urlparse(url)
            host = _host(url)
            if parsed.scheme not in {"http", "https"} or not host or host == article_host or _ignored_host(host) or parsed.path.lower().endswith(_IGNORED_EXTENSIONS):
                continue
            if url not in seen:
                seen.add(url)
                links.append(url)
            if len(links) >= self.max_links_per_announcement:
                break
        return links

    async def _direct_product(self, url: str, *, announcement: ProductObservation) -> tuple[list[ProductObservation], SourceCandidate]:
        host = _host(url)
        source = dynamic_source_name("jsonld", url)
        score = 0.68 + (0.08 if _PRODUCT_PATH.search(urlparse(url).path) else 0.0)
        try:
            text = await self._text(url, source="auto-source-direct")
            products = await asyncio.to_thread(_parse_jsonld_page, source, url, text)
        except Exception as exc:
            self._errors[url] = f"{type(exc).__name__}: {exc}"
            return [], SourceCandidate(host, url, "manufacturer_page", announcement.listing_url, score, "candidate", False, {"reason": "outbound_link", "probe_error": self._errors[url]})
        if not products:
            return [], SourceCandidate(host, url, "manufacturer_page", announcement.listing_url, score, "candidate", False, {"reason": "outbound_link", "product_jsonld": False})
        enriched: list[ProductObservation] = []
        for item in products:
            attrs = dict(item.attributes)
            attrs.update({"auto_discovered": True, "discovery_kind": "verified_manufacturer_product", "discovered_from": announcement.listing_url, "manufacturer_domain": host, "verification": "schema.org/Product"})
            enriched.append(replace(item, source=source, attributes=attrs))
        return enriched, SourceCandidate(host, url, "jsonld", announcement.listing_url, 1.0, "verified", False, {"reason": "outbound_link", "product_jsonld": True, "products": len(enriched)})

    async def _robots_sitemaps(self, origin: str) -> list[str]:
        try:
            text = await self._text(origin + "/robots.txt", source="auto-source-robots")
        except Exception:
            return []
        values: list[str] = []
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip().lower() == "sitemap" and value.strip().startswith(("http://", "https://")):
                values.append(value.strip())
        return list(dict.fromkeys(values))

    async def _homepage_surfaces(self, origin: str) -> tuple[list[str], list[str]]:
        try:
            text = await self._text(origin + "/", source="auto-source-home")
        except Exception:
            return [], []
        parser = _SurfaceParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        feeds = [urljoin(origin + "/", href) for _, href in parser.alternates]
        categories: list[str] = []
        for value in extract_html_links(origin + "/", text):
            if _host(value) == _host(origin) and _CATEGORY_PATH.search(urlparse(value).path):
                normalized = canonical_url(value)
                if normalized not in categories:
                    categories.append(normalized)
                if len(categories) >= 4:
                    break
        return feeds, categories

    async def _probe_sitemap(self, url: str, *, discovered_from: str, score: float) -> SourceCandidate | None:
        try:
            text = await self._text(url, source="auto-source-sitemap")
            pages, children = await asyncio.to_thread(extract_xml_links, text, "sitemap")
        except (Exception, ET.ParseError) as exc:
            self._errors[url] = f"{type(exc).__name__}: {exc}"
            return None
        if not pages and not children:
            return None
        productish = sum(1 for value in pages[:200] if _PRODUCT_PATH.search(urlparse(value).path))
        return SourceCandidate(_host(url), url, "sitemap", discovered_from, min(1.0, score + min(0.08, productish * 0.01)), "verified", True, {"urls_sampled": min(len(pages), 200), "child_sitemaps": len(children), "productish_urls": productish})

    async def _probe_feed(self, url: str, *, discovered_from: str, score: float) -> SourceCandidate | None:
        try:
            text = await self._text(url, source="auto-source-feed")
            pages, _ = await asyncio.to_thread(extract_xml_links, text, "feed")
        except (Exception, ET.ParseError) as exc:
            self._errors[url] = f"{type(exc).__name__}: {exc}"
            return None
        if not pages:
            return None
        return SourceCandidate(_host(url), url, "feed", discovered_from, score, "verified", True, {"entry_links": len(pages)})

    async def _probe_category(self, url: str, *, discovered_from: str, score: float) -> SourceCandidate | None:
        try:
            text = await self._text(url, source="auto-source-category")
        except Exception as exc:
            self._errors[url] = f"{type(exc).__name__}: {exc}"
            return None
        host = _host(url)
        links = [value for value in extract_html_links(url, text) if _host(value) == host and _PRODUCT_PATH.search(urlparse(value).path)]
        unique = list(dict.fromkeys(canonical_url(value) for value in links))
        if len(unique) < 2:
            return None
        return SourceCandidate(host, url, "html_index", discovered_from, min(1.0, score + min(0.1, len(unique) * 0.005)), "verified", True, {"productish_links": len(unique)})

    async def _probe_domain(self, origin: str, *, discovered_from: str) -> list[SourceCandidate]:
        probes = 0
        candidates: list[SourceCandidate] = []
        sitemaps = await self._robots_sitemaps(origin)
        feeds, categories = await self._homepage_surfaces(origin)
        common_sitemaps = [origin + "/sitemap.xml", origin + "/sitemap_index.xml", origin + "/sitemap-index.xml", origin + "/wp-sitemap.xml", origin + "/product-sitemap.xml", origin + "/products-sitemap.xml"]
        common_feeds = [origin + "/feed/", origin + "/feed.xml", origin + "/rss.xml", origin + "/atom.xml"]
        for url in list(dict.fromkeys(sitemaps + common_sitemaps)):
            if probes >= self.max_surface_probes_per_domain:
                break
            probes += 1
            result = await self._probe_sitemap(url, discovered_from=discovered_from, score=0.94 if url in sitemaps else 0.84)
            if result is not None:
                candidates.append(result)
        for url in list(dict.fromkeys(feeds + common_feeds)):
            if probes >= self.max_surface_probes_per_domain:
                break
            probes += 1
            result = await self._probe_feed(url, discovered_from=discovered_from, score=0.86 if url in feeds else 0.72)
            if result is not None:
                candidates.append(result)
        for url in categories:
            if probes >= self.max_surface_probes_per_domain:
                break
            probes += 1
            result = await self._probe_category(url, discovered_from=discovered_from, score=0.8)
            if result is not None:
                candidates.append(result)
        return candidates

    async def expand(self, announcements: Sequence[ProductObservation], *, known_hosts: Iterable[str] = ()) -> ExpansionResult:
        known = {_host(value) if "://" in value else str(value).lower().lstrip("www.") for value in known_hosts}
        product_map: dict[tuple[str, str], ProductObservation] = {}
        candidate_map: dict[tuple[str, str], SourceCandidate] = {}
        domains: dict[str, tuple[str, str]] = {}
        for announcement in announcements[: self.max_announcements]:
            for link in self._announcement_links(announcement):
                host = _host(link)
                products, direct_candidate = await self._direct_product(link, announcement=announcement)
                candidate_map[(direct_candidate.source_type, canonical_url(direct_candidate.source_url))] = direct_candidate
                for product in products:
                    product_map[product.identity] = product
                    if len(product_map) >= self.max_products_per_cycle:
                        break
                origin = _origin(link)
                if origin and host not in domains and host not in known:
                    domains[host] = (origin, announcement.listing_url)
                if len(domains) >= self.max_domains_per_cycle or len(product_map) >= self.max_products_per_cycle:
                    break
            if len(domains) >= self.max_domains_per_cycle or len(product_map) >= self.max_products_per_cycle:
                break
        probed = 0
        for _name, (origin, discovered_from) in list(domains.items())[: self.max_domains_per_cycle]:
            probed += 1
            for candidate in await self._probe_domain(origin, discovered_from=discovered_from):
                key = (candidate.source_type, canonical_url(candidate.source_url))
                current = candidate_map.get(key)
                if current is None or candidate.score > current.score:
                    candidate_map[key] = candidate
        return ExpansionResult(products=tuple(product_map.values()), candidates=tuple(sorted(candidate_map.values(), key=lambda item: (-item.score, item.source_type, item.source_url))), domains_considered=len(domains), domains_probed=probed, pages_probed=self._pages_probed, errors=dict(self._errors))
