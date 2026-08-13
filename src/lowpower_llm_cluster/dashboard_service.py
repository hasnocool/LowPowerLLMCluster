from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from aiohttp import web

from .catalog import load_catalog
from .dashboard import render_catalog_dashboard


DEFAULT_OUTPUT = "results/catalog-dashboard.html"


def render_dashboard_snapshot(output: str | Path = DEFAULT_OUTPUT) -> Path:
    """Render the current catalog dashboard and return the generated HTML path."""
    destination = Path(output).expanduser().resolve()
    catalog = load_catalog()
    parts = list(catalog.get("parts", []))
    return render_catalog_dashboard(parts, destination)


async def _refresh_snapshot(app: web.Application) -> None:
    output: Path = app["dashboard_output"]
    interval = float(app["dashboard_refresh_interval"])
    while True:
        try:
            await asyncio.to_thread(render_dashboard_snapshot, output)
            app["dashboard_last_error"] = None
        except Exception as exc:  # keep serving the last known-good snapshot
            app["dashboard_last_error"] = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(interval)


async def _startup(app: web.Application) -> None:
    output: Path = app["dashboard_output"]
    await asyncio.to_thread(render_dashboard_snapshot, output)
    app["dashboard_refresh_task"] = asyncio.create_task(_refresh_snapshot(app))


async def _cleanup(app: web.Application) -> None:
    task: asyncio.Task[Any] | None = app.get("dashboard_refresh_task")
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _index(request: web.Request) -> web.Response:
    output: Path = request.app["dashboard_output"]
    if not output.exists():
        await asyncio.to_thread(render_dashboard_snapshot, output)
    html = await asyncio.to_thread(output.read_text, encoding="utf-8")
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


async def _health(request: web.Request) -> web.Response:
    output: Path = request.app["dashboard_output"]
    error = request.app.get("dashboard_last_error")
    return web.json_response({
        "status": "ok" if output.exists() and error is None else "degraded",
        "dashboard": str(output),
        "snapshot_exists": output.exists(),
        "last_refresh_error": error,
    }, status=200 if output.exists() else 503)


def create_dashboard_app(*, output: str | Path = DEFAULT_OUTPUT, refresh_interval: float = 60.0) -> web.Application:
    if refresh_interval <= 0:
        raise ValueError("refresh_interval must be positive")
    app = web.Application()
    app["dashboard_output"] = Path(output).expanduser().resolve()
    app["dashboard_refresh_interval"] = float(refresh_interval)
    app["dashboard_last_error"] = None
    app.router.add_get("/", _index)
    app.router.add_get("/index.html", _index)
    app.router.add_get("/healthz", _health)
    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the LowPowerLLMCluster catalog dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="static HTML snapshot path")
    parser.add_argument("--refresh-interval", "--interval", dest="refresh_interval", type=float, default=60.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = create_dashboard_app(output=args.output, refresh_interval=args.refresh_interval)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
