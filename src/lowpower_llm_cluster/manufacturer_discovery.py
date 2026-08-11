from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree

import httpx

from .catalog import project_root

USER_AGENT = "LowPowerLLMCluster/0.5 (+https://github.com/hasnocool/LowPowerLLMCluster)"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").replace("_", " ").split())


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _norm(value))


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _norm(value)) if len(token) >= 3}


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        values = {key.casefold(): value for key, value in attrs}
        href = values.get("href")
        if href:
            self.links.append(str(href))


def load_discovery_config(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "market" / "manufacturer-discovery.json"
    return _load(target, {"schema_version": 1, "manufacturers": [], "policy": {}})


def _manufacturer_identity(listing: dict[str, Any], config: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
    product = listing.get("configuration") or {}
    raw_manufacturer = str(product.get("manufacturer") or listing.get("manufacturer") or "").strip()
    mpn = str(product.get("mpn") or listing.get("sku") or "").strip() or None
    title = _norm(listing.get("title"))
    best: tuple[int, dict[str, Any]] | None = None
    for entry in config.get("manufacturers", []):
        aliases = [str(entry.get("name") or "")] + [str(value) for value in entry.get("aliases", [])]
        score = 0
        if raw_manufacturer:
            raw = _compact(raw_manufacturer)
            if any(raw == _compact(alias) for alias in aliases if alias):
                score = 100
        if not score:
            score = max((len(_norm(alias)) for alias in aliases if alias and _norm(alias) in title), default=0)
        if score and (best is None or score > best[0]):
            best = (score, entry)
    if best is None:
        return raw_manufacturer or None, mpn, None
    return str(best[1].get("name") or raw_manufacturer), mpn, dict(best[1])


def _official_host(url: str, entry: dict[str, Any]) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return any(host == str(domain).casefold() or host.endswith("." + str(domain).casefold()) for domain in entry.get("domains", []))


def association_cache_key(component: str, manufacturer: str | None, mpn: str | None, title: str | None) -> str:
    stable_product_identity = _compact(mpn) if mpn else _compact(title)
    identity = "|".join([component, _compact(manufacturer), stable_product_identity])
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _parse_when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def cached_association(component: str, listing: dict[str, Any], config: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any] | None:
    manufacturer, mpn, _ = _manufacturer_identity(listing, config)
    key = association_cache_key(component, manufacturer, mpn, listing.get("title"))
    row = (cache.get("associations") or {}).get(key)
    if not row:
        return None
    checked = _parse_when(row.get("verified_at") or row.get("checked_at"))
    ttl_days = float((config.get("policy") or {}).get("cache_ttl_days", 30))
    if checked is None or checked < datetime.now(UTC) - timedelta(days=ttl_days):
        return None
    return dict(row)


def _identity_score(text: str, url: str, manufacturer: str | None, mpn: str | None, title: str | None) -> tuple[float, list[str]]:
    page = _norm(text)
    compact_page = _compact(text)
    reasons: list[str] = []
    score = 0.0
    if mpn:
        exact_mpn = _compact(mpn)
        if exact_mpn and exact_mpn in compact_page:
            score += 0.62
            reasons.append("mpn_on_page")
        if exact_mpn and exact_mpn in _compact(url):
            score += 0.12
            reasons.append("mpn_in_url")
    if manufacturer and _norm(manufacturer) in page:
        score += 0.12
        reasons.append("manufacturer_on_page")
    title_tokens = _tokens(title)
    if title_tokens:
        overlap = len(title_tokens & _tokens(text)) / len(title_tokens)
        score += min(0.18, overlap * 0.18)
        if overlap >= 0.5:
            reasons.append("title_token_match")
    return min(1.0, score), reasons


async def _robots_sitemaps(client: httpx.AsyncClient, domain: str) -> list[str]:
    urls: list[str] = []
    robots_url = f"https://{domain}/robots.txt"
    try:
        response = await client.get(robots_url)
        if response.status_code < 400:
            for line in response.text.splitlines():
                if line.casefold().startswith("sitemap:"):
                    value = line.split(":", 1)[1].strip()
                    if value.startswith("http"):
                        urls.append(value)
    except httpx.HTTPError:
        pass
    if not urls:
        urls.append(f"https://{domain}/sitemap.xml")
    return list(dict.fromkeys(urls))


async def _sitemap_candidates(client: httpx.AsyncClient, entry: dict[str, Any], mpn: str | None, title: str | None, policy: dict[str, Any]) -> list[str]:
    if not mpn and not title:
        return []
    wanted = {_compact(mpn)} if mpn else set()
    wanted |= {_compact(token) for token in _tokens(title) if len(token) >= 5}
    wanted.discard("")
    if not wanted:
        return []
    max_maps = int(policy.get("max_sitemaps_per_domain", 8))
    max_urls = int(policy.get("max_urls_scanned_per_domain", 12000))
    found: list[str] = []
    for domain in entry.get("domains", []):
        queue = await _robots_sitemaps(client, str(domain))
        seen: set[str] = set()
        scanned_urls = 0
        while queue and len(seen) < max_maps and scanned_urls < max_urls:
            sitemap_url = queue.pop(0)
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)
            try:
                response = await client.get(sitemap_url)
                if response.status_code >= 400:
                    continue
                content = response.content
                if sitemap_url.casefold().endswith(".gz"):
                    content = gzip.decompress(content)
                root = ElementTree.fromstring(content)
            except (httpx.HTTPError, OSError, ElementTree.ParseError):
                continue
            locs = [node.text.strip() for node in root.iter() if node.tag.casefold().endswith("loc") and node.text]
            if root.tag.casefold().endswith("sitemapindex"):
                queue.extend(url for url in locs if _official_host(url, entry))
                continue
            for url in locs:
                scanned_urls += 1
                if not _official_host(url, entry):
                    continue
                compact_url = _compact(url)
                if any(token and token in compact_url for token in wanted):
                    found.append(url)
                    if len(found) >= int(policy.get("max_candidate_urls", 10)):
                        return list(dict.fromkeys(found))
    return list(dict.fromkeys(found))


async def _search_page_candidates(client: httpx.AsyncClient, entry: dict[str, Any], query: str, policy: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for template in entry.get("search_url_templates", []):
        url = str(template).replace("{query}", quote_plus(query))
        if not _official_host(url, entry):
            continue
        try:
            response = await client.get(url)
            if response.status_code >= 400:
                continue
        except httpx.HTTPError:
            continue
        collector = LinkCollector(); collector.feed(response.text)
        for href in collector.links:
            candidate = urljoin(str(response.url), href)
            if _official_host(candidate, entry):
                found.append(candidate)
                if len(found) >= int(policy.get("max_candidate_urls", 10)):
                    return list(dict.fromkeys(found))
    return list(dict.fromkeys(found))


async def discover_manufacturer_association(
    component: str,
    listing: dict[str, Any],
    *,
    config_path: Path | None = None,
    cache_path: Path | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    config = load_discovery_config(config_path)
    cache_target = cache_path or project_root() / "data" / "market" / "manufacturer-associations.json"
    cache = _load(cache_target, {"schema_version": 1, "associations": {}})
    hit = cached_association(component, listing, config, cache)
    if hit:
        if hit.get("status") == "verified":
            hit["cache_hit"] = True
            return hit
        if hit.get("status") == "not_verified":
            return None
    manufacturer, mpn, entry = _manufacturer_identity(listing, config)
    if entry is None or not manufacturer:
        return None
    policy = config.get("policy") or {}
    if bool(policy.get("require_mpn", True)) and not mpn:
        return None
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=float(policy.get("timeout_seconds", 20)), follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        candidates: list[str] = []
        configuration = listing.get("configuration") or {}
        for hinted in (configuration.get("manufacturer_url"), listing.get("manufacturer_url")):
            if hinted and _official_host(str(hinted), entry):
                candidates.append(str(hinted))
        query = " ".join(value for value in (manufacturer, mpn, str(listing.get("title") or "")) if value)
        candidates.extend(await _search_page_candidates(client, entry, query, policy))
        candidates.extend(await _sitemap_candidates(client, entry, mpn, listing.get("title"), policy))
        candidates = list(dict.fromkeys(candidates))[: int(policy.get("max_candidate_urls", 10))]
        best: tuple[float, str, str, list[str]] | None = None
        for url in candidates:
            try:
                response = await client.get(url)
                if response.status_code >= 400 or not _official_host(str(response.url), entry):
                    continue
            except httpx.HTTPError:
                continue
            score, reasons = _identity_score(response.text, str(response.url), manufacturer, mpn, listing.get("title"))
            if best is None or score > best[0]:
                best = (score, str(response.url), response.text, reasons)
        minimum = float(policy.get("minimum_identity_score", 0.72))
        key = association_cache_key(component, manufacturer, mpn, listing.get("title"))
        if best is None or best[0] < minimum:
            cache.setdefault("associations", {})[key] = {"status": "not_verified", "component": component, "manufacturer": manufacturer, "mpn": mpn, "title": listing.get("title"), "checked_at": _now(), "candidate_count": len(candidates), "best_score": round(best[0], 3) if best else None}
            _write(cache_target, cache)
            return None
        row = {
            "status": "verified",
            "component": component,
            "manufacturer": manufacturer,
            "mpn": mpn,
            "title": listing.get("title"),
            "source_url": best[1],
            "identity_score": round(best[0], 3),
            "identity_reasons": best[3],
            "verified_at": _now(),
            "cache_hit": False,
            "discovery_method": "official_site_search_or_sitemap",
        }
        cache.setdefault("associations", {})[key] = row
        _write(cache_target, cache)
        row["page_html"] = best[2]
        return row
    finally:
        if owns_client:
            await client.aclose()
