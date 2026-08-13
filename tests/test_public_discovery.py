from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web

from lowpower_llm_cluster.http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from lowpower_llm_cluster.public_discovery import PublicWebDiscoveryAdapter, extract_html_links, extract_xml_links, parse_page_metadata


def test_extract_public_index_formats() -> None:
    links = extract_html_links("https://shop.test/category", '<a href="/Products/MX123">One</a><a href="https://other.test/x">Other</a>')
    assert links == ["https://shop.test/Products/MX123", "https://other.test/x"]

    pages, children = extract_xml_links(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://shop.test/p/1</loc></url></urlset>',
        "sitemap",
    )
    assert pages == ["https://shop.test/p/1"]
    assert children == []

    pages, children = extract_xml_links(
        '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://shop.test/products.xml</loc></sitemap></sitemapindex>',
        "sitemap",
    )
    assert pages == []
    assert children == ["https://shop.test/products.xml"]

    pages, _ = extract_xml_links('<rss><channel><item><link>https://shop.test/p/2</link></item></channel></rss>', "feed")
    assert pages == ["https://shop.test/p/2"]


def test_page_metadata_fallback_preserves_announcement_provenance() -> None:
    record = parse_page_metadata(
        "hardware-news",
        "https://news.test/new-edge-board",
        '<html><head><title>Fallback title</title><meta property="og:title" content="New Edge Board"><meta property="og:description" content="A 12 TOPS edge AI board"><meta property="article:published_time" content="2026-08-13T10:00:00Z"></head></html>',
        discovery_kind="announcement",
    )
    assert record is not None
    assert record.title == "New Edge Board"
    assert record.price is None
    assert record.attributes["discovery_kind"] == "announcement"
    assert record.attributes["published_at"] == "2026-08-13T10:00:00Z"
    assert record.attributes["metadata_fallback"] is True


def test_html_index_discovers_and_parses_public_product(tmp_path: Path) -> None:
    async def scenario() -> None:
        product_html = """<!doctype html><html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Tiny AI PC","sku":"TPC-1","mpn":"TPC-1","brand":{"@type":"Brand","name":"Example"},"offers":{"@type":"Offer","price":"399.99","priceCurrency":"CAD","availability":"https://schema.org/InStock","url":"/Products/MX123"}}</script></head><body></body></html>"""
        async def category(_: web.Request) -> web.Response:
            return web.Response(text='<a href="/Products/MX123">Tiny AI PC</a><a href="/support">Support</a>', content_type="text/html")
        async def product(_: web.Request) -> web.Response:
            return web.Response(text=product_html, content_type="text/html")
        app = web.Application(); app.router.add_get("/Category/Computers", category); app.router.add_get("/Products/MX123", product)
        runner = web.AppRunner(app); await runner.setup(); site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]; base = f"http://127.0.0.1:{port}"
        cache = await DiscoveryCache.open(tmp_path / "cache.json"); limiter = AdaptiveConcurrency(minimum=1, maximum=2, initial=2)
        try:
            async with AsyncHttpClient(concurrency=4, per_host=2) as client:
                adapter = PublicWebDiscoveryAdapter(name="fixture-public", mode="html_index", seeds=[f"{base}/Category/Computers"], client=client, cache=cache, adaptive=limiter, include_patterns=[r"/Products/MX[0-9]+$"], max_candidate_pages=10, subworkers=2, batch_size=2)
                assert await adapter.discover_urls() == [f"{base}/Products/MX123"]
                records = await adapter.discover(); assert len(records) == 1
                record = records[0]; assert record.title == "Tiny AI PC"; assert record.price == 399.99; assert record.currency == "CAD"; assert record.sku == "TPC-1"; assert record.in_stock is True
        finally:
            await runner.cleanup()
    asyncio.run(scenario())


def test_announcement_index_keeps_article_without_product_jsonld(tmp_path: Path) -> None:
    async def scenario() -> None:
        async def index(_: web.Request) -> web.Response:
            return web.Response(text='<a href="/new-risc-v-ai-board/">New board</a>', content_type="text/html")
        async def article(_: web.Request) -> web.Response:
            return web.Response(text='<html><head><meta property="og:title" content="RISC-V AI Board Arrives"><meta property="og:description" content="New compact AI SBC"><meta property="article:published_time" content="2026-08-13T12:00:00Z"></head></html>', content_type="text/html")
        app = web.Application(); app.router.add_get("/", index); app.router.add_get("/new-risc-v-ai-board/", article)
        runner = web.AppRunner(app); await runner.setup(); site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]; base = f"http://127.0.0.1:{port}"
        cache = await DiscoveryCache.open(tmp_path / "announcement-cache.json"); limiter = AdaptiveConcurrency(minimum=1, maximum=2, initial=2)
        try:
            async with AsyncHttpClient(concurrency=4, per_host=2) as client:
                adapter = PublicWebDiscoveryAdapter(name="fixture-news", mode="announcement_index", seeds=[f"{base}/"], client=client, cache=cache, adaptive=limiter, include_patterns=[r"/new-risc-v-ai-board/$"], max_candidate_pages=5, subworkers=2, fallback_page_metadata=True, discovery_kind="announcement")
                records = await adapter.discover(); assert len(records) == 1
                assert records[0].title == "RISC-V AI Board Arrives"; assert records[0].attributes["discovery_kind"] == "announcement"; assert records[0].price is None
        finally:
            await runner.cleanup()
    asyncio.run(scenario())
