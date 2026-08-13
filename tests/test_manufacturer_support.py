import asyncio

import httpx

from lowpower_llm_cluster.manufacturer_support import ingest_support_endpoint, pagination_metadata


def test_total_count_can_prove_last_page():
    meta = pagination_metadata({"totalCount": 4, "page": 2, "pageSize": 2}, rows_on_page=2, page=2)
    assert meta["complete"] is True
    assert meta["proof"] == "explicit_total_count"


def test_paginated_json_matrix_is_complete_only_after_all_pages():
    pages = {
        "1": {"items": [{"cpu": "Ryzen 5 5600", "bios": "A9"}, {"cpu": "Ryzen 7 5700X", "bios": "A9"}], "page": 1, "pageSize": 2, "totalCount": 3, "hasMore": True},
        "2": {"items": [{"cpu": "Ryzen 7 5800X3D", "bios": "AB"}], "page": 2, "pageSize": 2, "totalCount": 3, "hasMore": False},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        return httpx.Response(200, json=pages[page], request=request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ingest_support_endpoint("https://www.msi.com/support/cpu?page=1", client=client, expected_host="msi.com")

    result = asyncio.run(run())
    assert result["complete"] is True
    assert result["completeness_proof"] in {"explicit_total_count", "explicit_has_more_false"}
    assert result["row_count"] == 3
    assert result["pages_fetched"] == 2


def test_plain_html_matrix_remains_partial_without_explicit_proof():
    html = """<table><tr><th>CPU</th><th>BIOS</th></tr><tr><td>Ryzen 5 5600</td><td>A9</td></tr></table>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"}, request=request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ingest_support_endpoint("https://www.gigabyte.com/support/cpu", client=client, expected_host="gigabyte.com")

    result = asyncio.run(run())
    assert result["row_count"] == 1
    assert result["complete"] is False


def test_official_host_boundary_is_enforced():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request))) as client:
            return await ingest_support_endpoint("https://example.net/cpu", client=client, expected_host="asus.com")

    result = asyncio.run(run())
    assert result["status"] == "rejected"
    assert result["complete"] is False
