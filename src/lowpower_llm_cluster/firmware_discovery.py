from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .manufacturer_support import ingest_support_endpoint, manufacturer_family

MAX_DISCOVERY_URLS = 24
MAX_DISCOVERY_FETCHES = 8
MAX_BIOS_ROWS = 256

PROVIDER_PATH_HINTS: dict[str, tuple[str, ...]] = {
    "asus": ("supportonly/{model}/helpdesk_cpu/", "supportonly/{model}/helpdesk_bios/", "motherboards-components/motherboards/{model}/helpdesk_bios/"),
    "msi": ("Motherboard/{model}/support", "Motherboard/{model}/support#cpu", "Motherboard/{model}/support#bios"),
    "gigabyte": ("Motherboard/{model}/support#support-cpu", "Motherboard/{model}/support#support-dl-bios"),
    "asrock": ("mb/{model}/index.asp#CPU", "mb/{model}/index.asp#BIOS"),
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").replace("_", " ").split())


def _same_host(url: str, host: str) -> bool:
    candidate = (urlparse(url).hostname or "").casefold()
    expected = host.casefold()
    return bool(candidate and expected and (candidate == expected or candidate.endswith("." + expected)))


class _DiscoveryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self._script = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.casefold(): (v or "") for k, v in attrs}
        if tag.casefold() == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag.casefold() == "script":
            self._script = True
            self._chunks = []
            if values.get("src"):
                self.links.append(values["src"])

    def handle_data(self, data: str) -> None:
        if self._script:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._script:
            self.scripts.append("".join(self._chunks))
            self._script = False
            self._chunks = []


def product_model_tokens(source_url: str, html: str) -> list[str]:
    tokens: list[str] = []
    path_parts = [part for part in urlparse(source_url).path.split("/") if part]
    for part in reversed(path_parts):
        if 4 <= len(part) <= 80 and any(ch.isdigit() for ch in part):
            tokens.append(part)
            break
    for pattern in (r'"(?:model|mpn|sku)"\s*:\s*"([^"]{3,80})"', r'\b([A-Z]{1,5}[A-Z0-9-]{3,30})\b'):
        for match in re.findall(pattern, html, re.IGNORECASE):
            if any(ch.isdigit() for ch in str(match)):
                tokens.append(str(match))
            if len(tokens) >= 8:
                break
    return list(dict.fromkeys(tokens))[:8]


def discover_unlinked_candidates(html: str, source_url: str, *, official_host: str | None = None) -> list[dict[str, Any]]:
    """Generate official support/API candidates from product identity, scripts, and provider path conventions."""
    host = (official_host or urlparse(source_url).hostname or "").casefold()
    if not host:
        return []
    parser = _DiscoveryParser(); parser.feed(html)
    provider = manufacturer_family(source_url)
    models = product_model_tokens(source_url, html)
    candidates: dict[str, dict[str, Any]] = {}

    def add(url: str, score: int, basis: str, kinds: list[str]) -> None:
        absolute = urljoin(source_url, url)
        if not absolute.startswith("https://") or not _same_host(absolute, host):
            return
        current = candidates.get(absolute)
        row = {"url": absolute, "score": score, "basis": basis, "kinds": sorted(set(kinds)), "linked": False}
        if current is None or score > int(current.get("score") or 0): candidates[absolute] = row

    for model in models:
        safe = model.strip("/ ")
        for template in PROVIDER_PATH_HINTS.get(provider, ()):
            add(urljoin(f"https://{host}/", template.format(model=safe)), 68, "provider_product_support_pattern", ["cpu_support", "bios"])

    # Inline scripts frequently expose XHR/JSON support endpoints not rendered as anchors.
    script_text = "\n".join(parser.scripts)
    for match in re.findall(r'["\'](https?://[^"\']+|/[^"\']{3,180})["\']', script_text):
        text = _norm(match)
        if any(term in text for term in ("cpu support", "cpusupport", "processor", "bios", "firmware", "support api", "supportapi")):
            kinds = ["cpu_support"] if any(term in text for term in ("cpu", "processor")) else []
            if any(term in text for term in ("bios", "firmware")): kinds.append("bios")
            add(match, 82 if "api" in text else 72, "inline_script_endpoint", kinds or ["downloads"])

    # robots/sitemap URLs are fetched by the async discovery function; normal page links are useful seed surfaces too.
    for href in parser.links:
        text = _norm(href)
        if any(term in text for term in ("cpu", "processor", "bios", "firmware", "support")):
            add(href, 55, "page_resource_hint", ["cpu_support"] if "cpu" in text or "processor" in text else ["bios"])
    return sorted(candidates.values(), key=lambda row: (-int(row["score"]), row["url"]))[:MAX_DISCOVERY_URLS]


def _sitemap_urls(text: str, source_url: str, host: str, model_tokens: list[str]) -> list[str]:
    urls = re.findall(r"<loc>\s*([^<]+)\s*</loc>", text, re.IGNORECASE)
    wanted: list[str] = []
    norm_models = [_norm(token) for token in model_tokens]
    for raw in urls:
        url = raw.strip()
        if not _same_host(url, host): continue
        normalized = _norm(urlparse(url).path)
        if not any(term in normalized for term in ("support", "cpu", "bios", "firmware", "download")): continue
        if norm_models and not any(token in normalized for token in norm_models): continue
        wanted.append(url)
        if len(wanted) >= MAX_DISCOVERY_URLS: break
    return wanted


async def discover_unlinked_support_surfaces(source_url: str, html: str, *, client: httpx.AsyncClient, official_host: str | None = None) -> dict[str, Any]:
    host = (official_host or urlparse(source_url).hostname or "").casefold()
    candidates = discover_unlinked_candidates(html, source_url, official_host=host)
    models = product_model_tokens(source_url, html)
    discovery_sources: list[str] = []
    for path in ("/robots.txt", "/sitemap.xml"):
        try:
            response = await client.get(urljoin(f"https://{host}/", path)); response.raise_for_status()
        except httpx.HTTPError:
            continue
        discovery_sources.append(str(response.url))
        text = response.text
        sitemap_refs = re.findall(r"(?im)^sitemap:\s*(https?://\S+)", text)
        sitemap_payloads = [text]
        for sitemap in sitemap_refs[:3]:
            if not _same_host(sitemap, host): continue
            try:
                child = await client.get(sitemap); child.raise_for_status(); sitemap_payloads.append(child.text); discovery_sources.append(str(child.url))
            except httpx.HTTPError: pass
        for payload in sitemap_payloads:
            for url in _sitemap_urls(payload, source_url, host, models):
                candidates.append({"url": url, "score": 64, "basis": "official_sitemap", "kinds": ["cpu_support", "bios"], "linked": False})
    dedup: dict[str, dict[str, Any]] = {}
    for row in candidates:
        if row["url"] not in dedup or int(row["score"]) > int(dedup[row["url"]]["score"]): dedup[row["url"]] = row
    return {"candidates": sorted(dedup.values(), key=lambda row: (-int(row["score"]), row["url"]))[:MAX_DISCOVERY_URLS], "discovery_sources": discovery_sources, "model_tokens": models, "official_host": host}


def normalize_bios_history_payload(payload: Any, *, source_url: str) -> list[dict[str, Any]]:
    """Extract BIOS release history from common JSON shapes without inferring ordering semantics."""
    rows: list[dict[str, Any]] = []
    def walk(value: Any) -> None:
        if isinstance(value, list):
            for child in value: walk(child)
        elif isinstance(value, dict):
            lower = {str(k).casefold(): v for k, v in value.items()}
            version = next((lower[k] for k in ("version", "bios", "bios_version", "name") if k in lower), None)
            date = next((lower[k] for k in ("date", "release_date", "released", "publishdate", "publish_date") if k in lower), None)
            file_url = next((lower[k] for k in ("url", "download", "download_url", "file", "file_url") if k in lower), None)
            if version is not None and (date is not None or file_url is not None):
                rows.append({"version": str(version).strip(), "release_date": str(date).strip() if date is not None else None, "download_url": urljoin(source_url, str(file_url)) if file_url else None, "source_url": source_url, "source_type": "manufacturer_bios_history", "confidence": "high"})
            for child in value.values(): walk(child)
    walk(payload)
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["version"]: dedup[row["version"].casefold()] = row
    return list(dedup.values())[:MAX_BIOS_ROWS]


def extract_board_revision_evidence(text: str, *, source_url: str) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    patterns = (
        r"(?:hardware|board|pcb)\s*(?:revision|rev\.?)[\s:#-]*([A-Z0-9.]+)",
        r"\brev\.?\s*([0-9]+(?:\.[0-9]+)+)\b",
    )
    for pattern in patterns:
        for value in re.findall(pattern, text, re.IGNORECASE):
            revisions.append({"revision": str(value).upper(), "source_url": source_url, "source_type": "manufacturer_revision_evidence", "confidence": "medium"})
    return list({row["revision"]: row for row in revisions}.values())


def shipped_bios_evidence(text: str, *, minimum_bios: str | None = None, source_url: str = "") -> dict[str, Any]:
    """Accept shipped/factory BIOS only from explicit wording; never infer from manufacture date alone."""
    patterns = (
        r"(?:ships?|shipped|factory|preinstalled|pre-installed)\s+(?:with\s+)?(?:bios|uefi)\s*(?:version)?\s*[:#-]?\s*([A-Z0-9._-]+)",
        r"(?:bios|uefi)\s*(?:version)?\s*([A-Z0-9._-]+)\s*(?:or later\s*)?(?:installed|preinstalled|from factory)",
    )
    version = None
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match: version = match.group(1); break
    if not version:
        return {"status": "unknown", "shipped_bios_version": None, "meets_minimum": None, "source_url": source_url, "confidence": "unknown"}
    # Version ordering is vendor-specific; exact equality is safe, other ordering requires a vendor comparator not provided here.
    meets = True if minimum_bios and _norm(version) == _norm(minimum_bios) else None
    return {"status": "explicit", "shipped_bios_version": version, "meets_minimum": meets, "minimum_bios_version": minimum_bios, "source_url": source_url, "confidence": "high", "warning": None if meets is True else "Shipped BIOS is explicit, but vendor-specific version ordering is not proven; minimum comparison remains unresolved."}


async def probe_unlinked_support_candidates(discovery: dict[str, Any], *, client: httpx.AsyncClient, max_fetches: int = MAX_DISCOVERY_FETCHES) -> dict[str, Any]:
    """Probe ranked official candidates for CPU matrices and BIOS histories."""
    host = str(discovery.get("official_host") or "")
    support_best: dict[str, Any] | None = None
    bios_rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for row in list(discovery.get("candidates") or [])[:max_fetches]:
        url = str(row.get("url") or "")
        if not _same_host(url, host): continue
        kinds = set(row.get("kinds") or [])
        if "cpu_support" in kinds:
            try: result = await ingest_support_endpoint(url, client=client, expected_host=host, max_pages=32)
            except (httpx.HTTPError, ValueError) as exc: result = {"status":"error","endpoint":url,"rows":[],"complete":False,"reason":f"{type(exc).__name__}: {exc}"}
            attempts.append({"url":url,"kind":"cpu_support","status":result.get("status"),"rows":len(result.get("rows") or []),"complete":bool(result.get("complete"))})
            if support_best is None or bool(result.get("complete")) or len(result.get("rows") or []) > len(support_best.get("rows") or []): support_best = result
            if result.get("complete"): pass
        if "bios" in kinds:
            try:
                response = await client.get(url); response.raise_for_status(); payload = response.json() if "json" in str(response.headers.get("content-type") or "").casefold() or response.text.lstrip().startswith(("{","[")) else None
                if payload is not None: bios_rows.extend(normalize_bios_history_payload(payload, source_url=str(response.url)))
                attempts.append({"url":url,"kind":"bios","status":"ok","rows":len(bios_rows)})
            except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                attempts.append({"url":url,"kind":"bios","status":"unparsed","rows":0})
    bios_dedup = list({row["version"].casefold(): row for row in bios_rows}.values())[:MAX_BIOS_ROWS]
    return {"support_matrix": list((support_best or {}).get("rows") or []), "support_complete": bool((support_best or {}).get("complete")), "support_completeness_proof": (support_best or {}).get("completeness_proof"), "support_endpoint": (support_best or {}).get("endpoint"), "bios_history": bios_dedup, "attempts": attempts}
