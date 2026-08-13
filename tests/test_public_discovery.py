from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web

from lowpower_llm_cluster.http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from lowpower_llm_cluster.public_discovery import PublicWebDiscoveryAdapter, extract_html_links, extract_xml_links


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

    pages, _ = extract_xml_links(
        '<rss><channel><item><link>https://shop.test/p/2</link></item></channel></rss>',
        "feed",
    )
    assert pages == ["https://shop.test/p/2"]


def test_html_index_discovers_and_parses_public_product(tmp_path: Path) -> None:
    async def scenario() -> None:
        product_html = """<!doctype html><html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"Tiny AI PC","sku":"TPC-1","mpn":"TPC-1","brand":{"@type":"Brand","name":"Example"},"offers":{"@type":"Offer","price":"399.99","priceCurrency":"CAD","availability":"https://schema.org/InStock","url":"/Products/MX123"}}
        </script></head><body></body></html>"""

        async def category(_: web.Request) -> web.Response:
            return web.Response(text='<a href="/Products/MX123">Tiny AI PC</a><a href="/support">Support</a>', content_type="text/html")

        async def product(_: web.Request) -> web.Response:
            return web.Response(text=product_html, content_type="text/html")

        app = web.Application()
        app.router.add_get("/Category/Computers", category)
        app.router.add_get("/Products/MX123", product)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        cache = await DiscoveryCache.open(tmp_path / "cache.json")
        limiter = AdaptiveConcurrency(minimum=1, maximum=2, initial=2)
        try:
            async with AsyncHttpClient(concurrency=4, per_host=2) as client:
                adapter = PublicWebDiscoveryAdapter(
                    name="fixture-public",
                    mode="html_index",
                    seeds=[f"{base}/Category/Computers"],
                    client=client,
                    cache=cache,
                    adaptive=limiter,
                    include_patterns=[r"/Products/MX[0-9]+$"],
                    max_candidate_pages=10,
                    subworkers=2,
                    batch_size=2,
                )
                urls = await adapter.discover_urls()
                assert urls == [f"{base}/Products/MX123"]
                records = await adapter.discover()
                assert len(records) == 1
                record = records[0]
                assert record.title == "Tiny AI PC"
                assert record.price == 399.99
                assert record.currency == "CAD"
                assert record.sku == "TPC-1"
                assert record.in_stock is True
        finally:
            await runner.cleanup()

    asyncio.run(scenario())
