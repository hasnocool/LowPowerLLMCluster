from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from aiohttp import web

from lowpower_llm_cluster.announcement_links import extract_vendor_links
from lowpower_llm_cluster.catalog_refresh import CatalogRefreshEngine
from lowpower_llm_cluster.config_loader import DEFAULT_AUTO_SOURCE_EXPANSION, load_discovery_config
from lowpower_llm_cluster.source_store import SourceCandidateStore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "discovery.example.json"


def test_extract_vendor_links_filters_noise() -> None:
    html = """
    <a href="/same-site">same</a>
    <a href="https://twitter.com/vendor">social</a>
    <a href="https://example-hardware.com/datasheet.pdf">pdf</a>
    <a href="https://example-hardware.com/products/edgebox">official</a>
    <a href="https://example-hardware.com/products/edgebox#specs">duplicate</a>
    """
    assert extract_vendor_links("https://linuxgizmos.test/article", html) == [
        "https://example-hardware.com/products/edgebox"
    ]


def test_default_config_enables_bounded_auto_expansion(tmp_path: Path) -> None:
    merged = load_discovery_config(DEFAULT_CONFIG)
    expansion = merged["auto_source_expansion"]
    assert expansion["enabled"] is True
    assert 1 <= int(expansion["max_domains_per_cycle"]) <= 8
    assert 1 <= int(expansion["max_surface_probes_per_domain"]) <= 12
    assert 1 <= int(expansion["max_dynamic_sources"]) <= 128
    assert DEFAULT_AUTO_SOURCE_EXPANSION["enabled"] is True

    custom = tmp_path / "discovery.json"
    custom.write_text(json.dumps({"sources": []}), encoding="utf-8")
    assert "auto_source_expansion" not in load_discovery_config(custom)


def test_source_candidate_store_preserves_verified_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SourceCandidateStore(tmp_path / "history.sqlite3")
        await store.initialize()
        verified = {
            "domain": "vendor.test",
            "source_url": "https://vendor.test/sitemap.xml",
            "source_type": "sitemap",
            "discovered_from": "https://news.test/item",
            "score": 0.94,
            "status": "verified",
            "active": True,
            "metadata": {"productish_urls": 4},
        }
        downgraded = {**verified, "score": 0.2, "status": "candidate", "active": False}
        await store.upsert([verified])
        await store.upsert([downgraded])
        active = await store.active(limit=10)
        assert len(active) == 1
        assert active[0]["status"] == "verified"
        assert active[0]["active"] is True
        assert active[0]["score"] == 0.94
        summary = await store.summary()
        assert summary["verified"] == 1
        assert summary["active"] == 1

    asyncio.run(scenario())


def test_continuous_engine_grows_sources_from_announcement(tmp_path: Path) -> None:
    async def scenario() -> None:
        state: dict[str, str] = {}

        async def news(_: web.Request) -> web.Response:
            return web.Response(text='<a href="/article">New edge computer</a>', content_type="text/html")

        async def article(_: web.Request) -> web.Response:
            return web.Response(
                text=f'''<!doctype html><html><head><title>New EdgeBox announced</title></head><body>
                <a href="http://localhost:{state["port"]}/products/edge-1">Official product</a>
                <a href="https://twitter.com/example">social</a>
                </body></html>''',
                content_type="text/html",
            )

        def product_html(name: str, sku: str, price: str) -> str:
            return f'''<!doctype html><html><head>
            <script type="application/ld+json">{{
              "@context":"https://schema.org","@type":"Product","name":"{name}",
              "sku":"{sku}","mpn":"{sku}","brand":{{"@type":"Brand","name":"FixtureVendor"}},
              "offers":{{"@type":"Offer","price":"{price}","priceCurrency":"USD",
                "availability":"https://schema.org/InStock"}}
            }}</script></head><body></body></html>'''

        async def product_one(_: web.Request) -> web.Response:
            return web.Response(text=product_html("EdgeBox One", "EDGE-1", "299"), content_type="text/html")

        async def product_two(_: web.Request) -> web.Response:
            return web.Response(text=product_html("EdgeBox Two", "EDGE-2", "399"), content_type="text/html")

        async def homepage(_: web.Request) -> web.Response:
            return web.Response(
                text=f'''<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head>
                <body><a href="/products">Products</a></body></html>''',
                content_type="text/html",
            )

        async def robots(_: web.Request) -> web.Response:
            return web.Response(text=f'Sitemap: http://localhost:{state["port"]}/sitemap.xml\n', content_type="text/plain")

        async def sitemap(_: web.Request) -> web.Response:
            return web.Response(
                text=f'''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <url><loc>http://localhost:{state["port"]}/products/edge-1</loc></url>
                <url><loc>http://localhost:{state["port"]}/products/edge-2</loc></url>
                </urlset>''',
                content_type="application/xml",
            )

        async def feed(_: web.Request) -> web.Response:
            return web.Response(
                text=f'''<rss><channel><item><link>http://localhost:{state["port"]}/products/edge-2</link></item></channel></rss>''',
                content_type="application/rss+xml",
            )

        async def products(_: web.Request) -> web.Response:
            return web.Response(
                text='<a href="/products/edge-1">One</a><a href="/products/edge-2">Two</a>',
                content_type="text/html",
            )

        app = web.Application()
        app.router.add_get("/news", news)
        app.router.add_get("/article", article)
        app.router.add_get("/products/edge-1", product_one)
        app.router.add_get("/products/edge-2", product_two)
        app.router.add_get("/", homepage)
        app.router.add_get("/robots.txt", robots)
        app.router.add_get("/sitemap.xml", sitemap)
        app.router.add_get("/feed.xml", feed)
        app.router.add_get("/products", products)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 0)
        await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]
        state["port"] = str(port)

        config = tmp_path / "fixture.json"
        config.write_text(json.dumps({
            "agent_workers": 2,
            "subworkers_per_agent": 2,
            "http_concurrency": 6,
            "http_per_host": 3,
            "sources": [{
                "name": "fixture-news",
                "type": "announcement_index",
                "source_trust": 0.6,
                "subworkers": 1,
                "seeds": [f"http://127.0.0.1:{port}/news"],
                "include_patterns": [rf"^http://127\.0\.0\.1:{port}/article$"],
                "same_host": True,
                "max_index_pages": 1,
                "max_candidate_pages": 4,
                "batch_size": 4,
            }],
            "auto_source_expansion": {
                "enabled": True,
                "max_announcements_per_cycle": 4,
                "max_links_per_announcement": 4,
                "max_domains_per_cycle": 2,
                "max_surface_probes_per_domain": 8,
                "max_verified_products_per_cycle": 8,
                "max_dynamic_sources": 8,
                "min_dynamic_source_score": 0.72,
                "max_candidate_pages_per_dynamic_source": 8,
                "announcement_workers": 1,
                "dynamic_subworkers": 1,
                "probe_concurrency": 2,
                "verified_product_trust": 0.92,
            },
        }), encoding="utf-8")

        history = tmp_path / "history.sqlite3"
        output = tmp_path / "output.json"
        cache = tmp_path / "cache.json"
        try:
            async with CatalogRefreshEngine(config, history_path=history, output_path=output, cache_path=cache) as engine:
                first = await engine.run_once()
                expansion = first["runtime"]["auto_source_expansion"]
                assert expansion["verified_products"] >= 1
                assert expansion["dynamic_sources_added"] >= 1
                assert first["runtime"]["dynamic_source_count"] >= 1
                initial_pipeline_sources = first["runtime"]["discovery"]["source_count"]

                second = await engine.run_once()
                assert second["runtime"]["discovery"]["source_count"] > initial_pipeline_sources
        finally:
            await runner.cleanup()

        connection = sqlite3.connect(history)
        try:
            payloads = [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM observations")]
            assert any(item.get("attributes", {}).get("discovery_kind") == "verified_manufacturer_product" for item in payloads)
            active = connection.execute(
                "SELECT COUNT(*) FROM source_candidates WHERE status='verified' AND active=1"
            ).fetchone()[0]
            assert active >= 1
        finally:
            connection.close()

    asyncio.run(scenario())
