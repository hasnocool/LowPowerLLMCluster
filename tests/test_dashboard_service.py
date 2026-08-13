from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import ClientSession, web

from lowpower_llm_cluster.dashboard_service import create_dashboard_app, render_dashboard_snapshot


def test_render_dashboard_snapshot_keeps_static_artifact(tmp_path: Path) -> None:
    output = render_dashboard_snapshot(tmp_path / "catalog-dashboard.html")
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "LowPowerLLMCluster Hardware Catalog" in html
    assert "Overview" in html


def test_dashboard_service_serves_html_and_health(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_dashboard_app(output=tmp_path / "dashboard.html", refresh_interval=3600)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        try:
            sockets = site._server.sockets  # type: ignore[union-attr]
            port = sockets[0].getsockname()[1]
            async with ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/") as response:
                    assert response.status == 200
                    assert "text/html" in response.headers["Content-Type"]
                    assert "LowPowerLLMCluster Hardware Catalog" in await response.text()
                async with session.get(f"http://127.0.0.1:{port}/healthz") as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["status"] == "ok"
                    assert payload["snapshot_exists"] is True
        finally:
            await runner.cleanup()

    asyncio.run(scenario())
