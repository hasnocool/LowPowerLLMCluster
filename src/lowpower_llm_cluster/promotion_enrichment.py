from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .canonical_promotion import evaluate
from .discovery import _parse_jsonld_page
from .manufacturer_identity import enrich_identity, official_product_url
from .normalization import normalize_observation


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    records: tuple[dict[str, Any], ...]
    attempted: int
    structured_products: int
    resolved_holds: int
    still_held: int
    errors: dict[str, str]


def _source_map(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in config.get("sources", []) if isinstance(config.get("sources"), list) else []:
        if isinstance(item, Mapping) and item.get("name"):
            result[str(item["name"])] = dict(item)
    return result


def _merge_normalized(base: Mapping[str, Any], enriched: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in enriched.items():
        if value not in (None, "", [], {}):
            result[key] = value
    raw = dict(base.get("raw_attributes") or {}) if isinstance(base.get("raw_attributes"), Mapping) else {}
    extra = enriched.get("raw_attributes")
    if isinstance(extra, Mapping):
        raw.update(extra)
    raw["metadata_fallback"] = False
    raw["structured_product_enriched"] = True
    raw["enrichment_method"] = "schema.org/Product"
    result["raw_attributes"] = raw
    return result


async def enrich_held_records(
    records: Sequence[Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    client: Any,
    max_refetch: int = 24,
    concurrency: int = 4,
    min_source_confidence: float = 0.80,
    min_sku_confidence: float = 0.55,
) -> EnrichmentResult:
    """Improve promotion evidence before relaxing any canonical gate.

    All records receive deterministic official-source manufacturer/URL identity
    enrichment. A bounded subset of still-held official product pages is then
    re-fetched and parsed specifically for schema.org Product metadata.
    """
    sources = _source_map(config)
    enriched = [enrich_identity(record, sources.get(str(record.get("source") or ""))) for record in records]
    before = [evaluate(row, min_source_confidence=min_source_confidence, min_sku_confidence=min_sku_confidence) for row in enriched]

    candidates: list[int] = []
    seen_urls: set[str] = set()
    for index, (row, reasons) in enumerate(zip(enriched, before)):
        if not reasons:
            continue
        url = str(row.get("listing_url") or "")
        source_cfg = sources.get(str(row.get("source") or ""))
        raw = row.get("raw_attributes") if isinstance(row.get("raw_attributes"), Mapping) else {}
        needs_structured = bool(raw.get("metadata_fallback") is True or "identity_confidence_below_threshold" in reasons or "missing_manufacturer" in reasons)
        if not needs_structured or not official_product_url(row, source_cfg) or url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append(index)
        if len(candidates) >= max(0, int(max_refetch)):
            break

    gate = asyncio.Semaphore(max(1, int(concurrency)))
    errors: dict[str, str] = {}
    structured = 0

    async def refetch(index: int) -> None:
        nonlocal structured
        row = enriched[index]
        source = str(row.get("source") or "")
        url = str(row.get("listing_url") or "")
        source_cfg = sources.get(source, {})
        trust = float(source_cfg.get("source_trust", row.get("source_confidence", 0.65) or 0.65))
        async with gate:
            try:
                response = await client.get_response(url, source=f"promotion-enrichment:{source}")
                text = response.payload.decode("utf-8", "replace")
                observations = await asyncio.to_thread(_parse_jsonld_page, source, url, text)
            except Exception as exc:
                errors[f"{source}|{url}"] = f"{type(exc).__name__}: {exc}"
                return
        if not observations:
            return
        best = max(observations, key=lambda obs: int(bool(obs.mpn)) * 3 + int(bool(obs.sku)) * 2 + int(bool(obs.manufacturer)))
        normalized = normalize_observation(best, source_trust=trust)
        enriched[index] = enrich_identity(_merge_normalized(row, normalized), source_cfg)
        structured += 1

    if candidates:
        await asyncio.gather(*(refetch(index) for index in candidates))

    after = [evaluate(row, min_source_confidence=min_source_confidence, min_sku_confidence=min_sku_confidence) for row in enriched]
    resolved = sum(1 for old, new in zip(before, after) if old and not new)
    return EnrichmentResult(
        records=tuple(enriched),
        attempted=len(candidates),
        structured_products=structured,
        resolved_holds=resolved,
        still_held=sum(1 for reasons in after if reasons),
        errors=errors,
    )
