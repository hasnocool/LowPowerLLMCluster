# src/lowpower_llm_cluster/manufacturer_support.py
from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx


MAX_SUPPORT_PAGES = 64


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def _same_host(url: str, expected_host: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    expected = expected_host.casefold()
    return bool(host and expected and (host == expected or host.endswith("." + expected)))


def manufacturer_family(url: str) -> str:
    host = (urlparse(url).hostname or "").casefold()
    if "asus." in host:
        return "asus"
    if "msi." in host:
        return "msi"
    if "gigabyte." in host or "aorus." in host:
        return "gigabyte"
    if "asrock." in host:
        return "asrock"
    return "generic"


def _first_key(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    lowered = {str(k).casefold(): v for k, v in row.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def _support_status(value: Any, bios: Any) -> str:
    text = _norm(value)
    if any(term in text for term in ("unsupported", "not supported", "not support", "no support")):
        return "unsupported"
    if text in {"no", "false", "0"}:
        return "unsupported"
    if any(term in text for term in ("supported", "support", "yes", "validated", "ok")):
        return "supported"
    if bios not in (None, "", "-", "n/a", "N/A"):
        return "supported"
    return "unknown"


def normalize_support_row(row: dict[str, Any], *, source_url: str, provider: str, page: int) -> dict[str, Any] | None:
    cpu = _first_key(row, ("cpu", "processor", "cpu_model", "model", "name", "cpuName", "processorName"))
    bios = _first_key(row, ("bios", "bios_version", "minimum_bios", "minimum_bios_version", "since_bios", "version", "supportBios"))
    status = _first_key(row, ("support", "status", "supported", "validation", "isSupported"))
    if cpu is None:
        return None
    cpu_text = str(cpu).strip()
    if not cpu_text:
        return None
    return {
        "cpu_model": cpu_text,
        "minimum_bios_version": str(bios).strip() if bios not in (None, "") else None,
        "support_status": _support_status(status, bios),
        "source_url": source_url,
        "source_type": "manufacturer_support_api",
        "extraction": f"{provider}_support_api",
        "provider": provider,
        "api_page": page,
        "confidence": "high",
    }


def _find_row_arrays(value: Any) -> list[list[dict[str, Any]]]:
    arrays: list[list[dict[str, Any]]] = []
    if isinstance(value, list):
        if value and all(isinstance(row, dict) for row in value):
            arrays.append(value)
        for item in value:
            arrays.extend(_find_row_arrays(item))
    elif isinstance(value, dict):
        for item in value.values():
            arrays.extend(_find_row_arrays(item))
    return arrays


def extract_json_support_rows(payload: Any, *, source_url: str, provider: str, page: int) -> list[dict[str, Any]]:
    candidates = _find_row_arrays(payload)
    normalized_sets: list[list[dict[str, Any]]] = []
    for rows in candidates:
        normalized = [item for row in rows if (item := normalize_support_row(row, source_url=source_url, provider=provider, page=page))]
        if normalized:
            normalized_sets.append(normalized)
    if not normalized_sets:
        return []
    return max(normalized_sets, key=len)


def pagination_metadata(payload: Any, *, rows_on_page: int, page: int) -> dict[str, Any]:
    """Return only explicit pagination/completeness evidence from the payload."""
    if not isinstance(payload, dict):
        return {"complete": False, "reason": "no_explicit_pagination_metadata"}

    def find(names: tuple[str, ...], value: Any) -> Any:
        if isinstance(value, dict):
            lowered = {str(k).casefold(): v for k, v in value.items()}
            for name in names:
                if name.casefold() in lowered:
                    return lowered[name.casefold()]
            for child in value.values():
                found = find(names, child)
                if found is not None:
                    return found
        return None

    total = find(("total", "total_count", "totalCount", "recordsTotal", "totalRecords"), payload)
    total_pages = find(("total_pages", "totalPages", "pageCount", "pages"), payload)
    current_page = find(("current_page", "currentPage", "page", "pageIndex"), payload)
    page_size = find(("page_size", "pageSize", "limit", "perPage"), payload)
    next_value = find(("next", "next_page", "nextPage", "nextPageUrl", "next_url"), payload)
    has_more = find(("has_more", "hasMore", "more"), payload)

    try:
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_i = None
    try:
        pages_i = int(total_pages) if total_pages is not None else None
    except (TypeError, ValueError):
        pages_i = None
    try:
        current_i = int(current_page) if current_page is not None else page
    except (TypeError, ValueError):
        current_i = page
    try:
        size_i = int(page_size) if page_size is not None else rows_on_page
    except (TypeError, ValueError):
        size_i = rows_on_page

    complete = False
    proof: str | None = None
    if pages_i is not None and pages_i > 0 and current_i >= pages_i:
        complete = True
        proof = "explicit_total_pages"
    elif total_i is not None and total_i >= 0 and size_i > 0 and (current_i * size_i) >= total_i:
        complete = True
        proof = "explicit_total_count"
    elif has_more is False:
        complete = True
        proof = "explicit_has_more_false"

    return {
        "complete": complete,
        "proof": proof,
        "total_count": total_i,
        "total_pages": pages_i,
        "current_page": current_i,
        "page_size": size_i,
        "next": next_value,
        "has_more": has_more,
    }


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.casefold()
        if lower == "table":
            self._table = []
        elif lower == "tr" and self._table is not None:
            self._row = []
        elif lower in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.casefold()
        if lower in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif lower == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif lower == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def extract_html_support_rows(html: str, *, source_url: str, provider: str, page: int) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    output: list[dict[str, Any]] = []
    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = [_norm(cell) for cell in table[0]]
        cpu_idx = next((index for index, cell in enumerate(headers) if any(term in cell for term in ("cpu", "processor", "model", "number"))), None)
        bios_idx = next((index for index, cell in enumerate(headers) if "bios" in cell), None)
        if cpu_idx is None or bios_idx is None:
            continue
        for row in table[1:]:
            if len(row) <= max(cpu_idx, bios_idx):
                continue
            item = normalize_support_row(
                {"cpu": row[cpu_idx], "bios": row[bios_idx]},
                source_url=source_url,
                provider=provider,
                page=page,
            )
            if item:
                output.append(item)
    return output


def _page_url(url: str, page: int, parameter: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[parameter] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def provider_page_parameter(provider: str) -> str:
    return {
        "asus": "page",
        "msi": "page",
        "gigabyte": "page",
        "asrock": "page",
    }.get(provider, "page")


async def ingest_support_endpoint(
    endpoint: str,
    *,
    client: httpx.AsyncClient,
    expected_host: str | None = None,
    max_pages: int = MAX_SUPPORT_PAGES,
) -> dict[str, Any]:
    """Fetch a manufacturer support endpoint and prove completeness only from explicit evidence."""
    host = (expected_host or urlparse(endpoint).hostname or "").casefold()
    if not endpoint.startswith("https://") or not host or not _same_host(endpoint, host):
        return {"status": "rejected", "rows": [], "complete": False, "reason": "endpoint_not_on_expected_official_host"}

    provider = manufacturer_family(endpoint)
    page_parameter = provider_page_parameter(provider)
    rows: list[dict[str, Any]] = []
    pages_fetched = 0
    proof: str | None = None
    explicit_total: int | None = None
    explicit_pages: int | None = None
    next_url: str | None = endpoint

    for page in range(1, min(max_pages, MAX_SUPPORT_PAGES) + 1):
        url = next_url or _page_url(endpoint, page, page_parameter)
        if not _same_host(url, host):
            break
        response = await client.get(url)
        response.raise_for_status()
        pages_fetched += 1
        content_type = str(response.headers.get("content-type") or "").casefold()
        payload: Any = None
        page_rows: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {"complete": False}
        if "json" in content_type or response.text.lstrip().startswith(("{", "[")):
            try:
                payload = response.json()
            except (json.JSONDecodeError, ValueError):
                payload = None
            if payload is not None:
                page_rows = extract_json_support_rows(payload, source_url=str(response.url), provider=provider, page=page)
                metadata = pagination_metadata(payload, rows_on_page=len(page_rows), page=page)
        if payload is None:
            page_rows = extract_html_support_rows(response.text, source_url=str(response.url), provider=provider, page=page)
            # Plain HTML is not called complete unless a provider-specific page explicitly says so.
            metadata = {"complete": False, "proof": None, "next": None}

        rows.extend(page_rows)
        explicit_total = metadata.get("total_count") if metadata.get("total_count") is not None else explicit_total
        explicit_pages = metadata.get("total_pages") if metadata.get("total_pages") is not None else explicit_pages
        if metadata.get("complete"):
            proof = str(metadata.get("proof") or "explicit_pagination_metadata")
            break
        raw_next = metadata.get("next")
        if isinstance(raw_next, str) and raw_next:
            candidate = urljoin(str(response.url), raw_next)
            next_url = candidate if _same_host(candidate, host) else None
        elif metadata.get("has_more") is True or (explicit_pages is not None and page < int(explicit_pages)):
            next_url = _page_url(endpoint, page + 1, page_parameter)
        else:
            next_url = None
            break

    dedup: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows:
        key = (_norm(row.get("cpu_model")), row.get("minimum_bios_version"))
        if key[0]:
            dedup[key] = row
    output = list(dedup.values())
    complete = proof is not None
    if explicit_total is not None and len(output) != int(explicit_total):
        complete = False
        proof = None
    return {
        "status": "complete" if complete else "partial",
        "provider": provider,
        "endpoint": endpoint,
        "rows": output,
        "row_count": len(output),
        "pages_fetched": pages_fetched,
        "complete": complete,
        "completeness_proof": proof,
        "explicit_total_count": explicit_total,
        "explicit_total_pages": explicit_pages,
    }


async def ingest_ranked_support_endpoints(
    endpoints: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient,
    official_host: str,
    max_endpoints: int = 4,
) -> dict[str, Any]:
    """Try ranked CPU-support endpoints and prefer the first explicitly complete matrix."""
    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    selected = [row for row in endpoints if "cpu_support" in set(row.get("kinds") or [])][:max_endpoints]
    for row in selected:
        try:
            result = await ingest_support_endpoint(str(row["url"]), client=client, expected_host=official_host)
        except (httpx.HTTPError, ValueError) as exc:
            result = {"status": "error", "endpoint": row.get("url"), "complete": False, "rows": [], "reason": f"{type(exc).__name__}: {exc}"}
        attempts.append({key: value for key, value in result.items() if key != "rows"})
        if best is None or len(result.get("rows") or []) > len(best.get("rows") or []):
            best = result
        if result.get("complete"):
            best = result
            break
    return {
        "matrix": list((best or {}).get("rows") or []),
        "complete": bool((best or {}).get("complete")),
        "completeness_proof": (best or {}).get("completeness_proof"),
        "selected_endpoint": (best or {}).get("endpoint"),
        "provider": (best or {}).get("provider"),
        "attempts": attempts,
    }
