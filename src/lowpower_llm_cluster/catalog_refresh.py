# src/lowpower_llm_cluster/catalog_refresh.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterable

from .discovery import AsyncHttpClient, DiscoveryPipeline, JsonFeedAdapter, JsonLdProductAdapter, ProductObservation
from .history import CatalogHistory
from .normalization import normalize_observation


def _dig(value: Any, path: str) -> Any:
    current = value
    for token in path.split(".") if path else ():
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _mapped_parser(source: dict[str, Any]):
    items_path = str(source.get("items_path", ""))
    fields: dict[str, str] = dict(source.get("fields", {}))
    constants: dict[str, Any] = dict(source.get("constants", {}))
    attribute_fields: dict[str, str] = dict(source.get("attribute_fields", {}))
    source_name = str(source["name"])

    def parse(payload: Any) -> Iterable[ProductObservation]:
        items = _dig(payload, items_path) if items_path else payload
        if isinstance(items, dict):
            items = list(items.values())
        for raw in items:
            values = {target: _dig(raw, path) for target, path in fields.items() if path}
            values.update(constants)
            attrs = {target: _dig(raw, path) for target, path in attribute_fields.items() if path}
            listing_url = str(values.get("listing_url", ""))
            source_id = str(values.get("source_id", "")) or listing_url
            yield ProductObservation(
                source=source_name,
                source_id=source_id,
                listing_url=listing_url,
                title=str(values.get("title", "")),
                price=float(values["price"]) if values.get("price") not in (None, "") else None,
                currency=str(values.get("currency", "USD")),
                shipping=float(values["shipping"]) if values.get("shipping") not in (None, "") else None,
                seller=str(values.get("seller", "")),
                seller_rating=float(values["seller_rating"]) if values.get("seller_rating") not in (None, "") else None,
                seller_review_count=int(values["seller_review_count"]) if values.get("seller_review_count") not in (None, "") else None,
                seller_verified=bool(values["seller_verified"]) if values.get("seller_verified") is not None else None,
                manufacturer=str(values.get("manufacturer", "")), sku=str(values.get("sku", "")), mpn=str(values.get("mpn", "")),
                in_stock=bool(values["in_stock"]) if values.get("in_stock") is not None else None,
                attributes=attrs,
            )
    return parse


async def run_discovery_config(config_path: Path | str, *, history_path: Path | str, output_path: Path | str) -> dict[str, Any]:
    config_path = Path(config_path)
    config = json.loads(await asyncio.to_thread(config_path.read_text, encoding="utf-8"))
    client = AsyncHttpClient(concurrency=int(config.get("concurrency", 4)), timeout_s=float(config.get("timeout_s", 20.0)))
    source_configs = list(config.get("sources", []))
    adapters = []
    trusts: dict[str, float] = {}
    for source in source_configs:
        source_type = str(source.get("type", "json"))
        name = str(source["name"])
        trusts[name] = float(source.get("source_trust", 0.65))
        if source_type == "json":
            adapters.append(JsonFeedAdapter(name=name, endpoint=str(source["endpoint"]), parser=_mapped_parser(source), client=client))
        elif source_type == "jsonld":
            urls = tuple(str(url) for url in source.get("urls", ()))
            if not urls:
                raise ValueError(f"jsonld source {name!r} requires urls")
            adapters.append(JsonLdProductAdapter(name=name, urls=urls, client=client))
        else:
            raise ValueError(f"unsupported source type {source_type!r}; built-ins are json and jsonld")

    result = await DiscoveryPipeline(adapters).run()
    history = CatalogHistory(history_path)
    await history.initialize()
    run_id, changes = await history.record_refresh(result.observations, source_names=[adapter.name for adapter in adapters], disappearance_after_runs=int(config.get("disappearance_after_runs", 2)))
    normalized = [normalize_observation(item, source_trust=trusts.get(item.source, 0.65)) for item in result.observations]
    payload = {
        "run_id": run_id,
        "observation_count": len(normalized),
        "errors": dict(result.errors),
        "changes": [
            {"source": change.source, "source_id": change.source_id, "change_type": change.change_type, "previous": change.previous, "current": change.current}
            for change in changes
        ],
        "observations": normalized,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(output_path.write_text, json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
