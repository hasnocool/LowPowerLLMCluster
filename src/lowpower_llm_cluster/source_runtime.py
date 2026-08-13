from __future__ import annotations

from typing import Any, Iterable

from .discovery import ProductObservation
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .process_adapter import ProcessAdapter
from .public_discovery import PublicWebDiscoveryAdapter
from .resilience_runtime import AdaptiveBatchSizer, CircuitBreaker
from .streaming_discovery import CachedJsonFeedAdapter, CachedJsonLdProductAdapter, CircuitProtectedAdapter, StreamingJsonFeedAdapter


def dig(value: Any, path: str) -> Any:
    current = value
    for token in path.split(".") if path else ():
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def mapped_item(source: dict[str, Any], raw: Any) -> ProductObservation:
    fields = dict(source.get("fields", {}))
    constants = dict(source.get("constants", {}))
    attribute_fields = dict(source.get("attribute_fields", {}))
    values = {target: dig(raw, path) for target, path in fields.items() if path}
    values.update(constants)
    attrs = {target: dig(raw, path) for target, path in attribute_fields.items() if path}
    listing_url = str(values.get("listing_url", ""))
    source_id = str(values.get("source_id", "")) or listing_url
    return ProductObservation(
        source=str(source["name"]), source_id=source_id, listing_url=listing_url,
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


def mapped_parser(source: dict[str, Any]):
    items_path = str(source.get("items_path", ""))
    def parse(payload: Any) -> Iterable[ProductObservation]:
        items = dig(payload, items_path) if items_path else payload
        if isinstance(items, dict):
            items = items.values()
        for raw in items:
            yield mapped_item(source, raw)
    return parse


def ijson_prefix(items_path: str) -> str:
    return f"{items_path}.item" if items_path else "item"


def build_source_adapter(source: dict[str, Any], *, settings: Any, client: AsyncHttpClient, cache: DiscoveryCache, adaptive: AdaptiveConcurrency, circuit: CircuitBreaker, batch_sizer: AdaptiveBatchSizer) -> Any:
    source_type = str(source.get("type", "json"))
    name = str(source["name"])
    batch_size = int(source.get("batch_size", batch_sizer.current))
    if source_type == "json":
        if bool(source.get("streaming_json", False)):
            inner = StreamingJsonFeedAdapter(name=name, endpoint=str(source["endpoint"]), items_prefix=str(source.get("ijson_prefix") or ijson_prefix(str(source.get("items_path", "")))), item_parser=lambda raw: mapped_item(source, raw), client=client, adaptive=adaptive, batch_size=batch_size, batch_sizer=batch_sizer)
        else:
            inner = CachedJsonFeedAdapter(name=name, endpoint=str(source["endpoint"]), parser=mapped_parser(source), client=client, cache=cache, adaptive=adaptive, batch_size=batch_size, queue_size=max(1, min(settings.queue_size, 32)), batch_sizer=batch_sizer)
    elif source_type == "jsonld":
        urls = tuple(str(url) for url in source.get("urls", ()))
        if not urls:
            raise ValueError(f"jsonld source {name!r} requires urls")
        inner = CachedJsonLdProductAdapter(name=name, urls=urls, client=client, cache=cache, adaptive=adaptive, subworkers=int(source.get("subworkers", settings.subworkers_per_agent)), queue_size=settings.queue_size, batch_sizer=batch_sizer)
    elif source_type in {"sitemap", "feed", "html_index"}:
        seeds = tuple(str(url) for url in source.get("seeds", source.get("urls", ())))
        if not seeds:
            raise ValueError(f"{source_type} source {name!r} requires seeds")
        inner = PublicWebDiscoveryAdapter(
            name=name,
            mode=source_type,
            seeds=seeds,
            client=client,
            cache=cache,
            adaptive=adaptive,
            include_patterns=tuple(str(value) for value in source.get("include_patterns", ())),
            exclude_patterns=tuple(str(value) for value in source.get("exclude_patterns", ())),
            same_host=bool(source.get("same_host", True)),
            max_candidate_pages=int(source.get("max_candidate_pages", 250)),
            max_index_pages=int(source.get("max_index_pages", 16)),
            subworkers=int(source.get("subworkers", settings.subworkers_per_agent)),
            batch_size=batch_size,
            batch_sizer=batch_sizer,
        )
    elif source_type == "process":
        command = tuple(str(value) for value in source.get("command", ()))
        if not command:
            raise ValueError(f"process source {name!r} requires command")
        inner = ProcessAdapter(name=name, command=command, source_config=source, timeout_s=float(source.get("process_timeout_s", 120)), batch_size=batch_size, max_line_bytes=int(source.get("process_max_line_bytes", 2 * 1024 * 1024)), batch_sizer=batch_sizer)
    else:
        raise ValueError(f"unsupported source type {source_type!r}; built-ins are json, jsonld, sitemap, feed, html_index and process")
    return CircuitProtectedAdapter(name=name, inner=inner, circuit=circuit)
