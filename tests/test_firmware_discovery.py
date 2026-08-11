from __future__ import annotations

import asyncio
import json

import httpx

from lowpower_llm_cluster.firmware_discovery import (
    discover_unlinked_candidates,
    discover_unlinked_support_surfaces,
    extract_board_revision_evidence,
    normalize_bios_history_payload,
    probe_unlinked_support_candidates,
    shipped_bios_evidence,
)


def test_inline_script_discovers_unlinked_official_cpu_api():
    html = '<script>const cpuApi="/api/support/cpu?model=B550-A-PRO";</script>'
    rows = discover_unlinked_candidates(html, "https://www.msi.com/Motherboard/B550-A-PRO", official_host="www.msi.com")
    assert any("/api/support/cpu" in row["url"] for row in rows)
    assert all("msi.com" in row["url"] for row in rows)


def test_third_party_script_endpoint_is_rejected():
    html = '<script>const cpuApi="https://evil.example/api/cpu-support";</script>'
    rows = discover_unlinked_candidates(html, "https://www.msi.com/Motherboard/B550-A-PRO", official_host="www.msi.com")
    assert not any("evil.example" in row["url"] for row in rows)


def test_bios_history_normalizer_preserves_versions_and_dates():
    payload = {"downloads": [{"version": "7C56vA9", "release_date": "2024-01-02", "url": "/bios/a9.zip"}, {"version": "7C56vAB", "release_date": "2025-02-03", "url": "/bios/ab.zip"}]}
    rows = normalize_bios_history_payload(payload, source_url="https://www.msi.com/api/bios")
    assert [row["version"] for row in rows] == ["7C56vA9", "7C56vAB"]
    assert rows[0]["download_url"] == "https://www.msi.com/bios/a9.zip"


def test_revision_and_explicit_shipped_bios_evidence():
    text = "PCB Rev. 1.2. This board ships with BIOS version A9 from factory."
    revisions = extract_board_revision_evidence(text, source_url="https://vendor.example/board")
    shipped = shipped_bios_evidence(text, minimum_bios="A9", source_url="https://vendor.example/board")
    assert revisions[0]["revision"] == "1.2"
    assert shipped["status"] == "explicit"
    assert shipped["meets_minimum"] is True


def test_manufacture_date_alone_does_not_infer_shipped_bios():
    shipped = shipped_bios_evidence("Manufactured 2025-08. Latest BIOS is AB.", minimum_bios="A9", source_url="https://vendor.example")
    assert shipped["status"] == "unknown"
    assert shipped["meets_minimum"] is None


def test_sitemap_discovery_and_probe_can_prove_complete_matrix():
    product = "https://vendor.example/board/B550-A-PRO"
    html = "<html><title>B550-A-PRO</title></html>"
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="Sitemap: https://vendor.example/sitemap.xml", request=request)
        if url.endswith("/sitemap.xml"):
            return httpx.Response(200, text="<urlset><url><loc>https://vendor.example/support/B550-A-PRO/cpu</loc></url></urlset>", request=request)
        if "/support/B550-A-PRO/cpu" in url:
            payload = {"rows": [{"cpu":"Ryzen 5 5600","bios":"A9"}], "totalCount":1, "page":1, "pageSize":20, "hasMore":False}
            return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type":"application/json"}, request=request)
        return httpx.Response(404, request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            discovery = await discover_unlinked_support_surfaces(product, html, client=client, official_host="vendor.example")
            result = await probe_unlinked_support_candidates(discovery, client=client)
            return discovery, result
    discovery, result = asyncio.run(run())
    assert any("support/B550-A-PRO/cpu" in row["url"] for row in discovery["candidates"])
    assert result["support_complete"] is True
    assert result["support_matrix"][0]["cpu_model"] == "Ryzen 5 5600"


def test_bios_api_preserves_revision_scoped_history():
    discovery = {"official_host": "vendor.example", "candidates": [{"url": "https://vendor.example/api/bios", "score": 90, "basis": "test", "kinds": ["bios"], "linked": False}]}
    payload = {"downloads": [{"version": "F14", "release_date": "2026-01-01", "url": "/f14.zip", "pcb_revision": "1.2"}]}
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type":"application/json"}, request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await probe_unlinked_support_candidates(discovery, client=client)
    result = asyncio.run(run())
    assert result["revision_bios_history"][0]["version"] == "F14"
    assert result["revision_bios_history"][0]["board_revisions"] == ["1.2"]
