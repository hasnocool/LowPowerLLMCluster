from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web

EXPECTED_TABLES = {"observations", "listing_state", "refresh_runs"}


def probe_history(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "compatible": False, "database_exists": False, "missing_tables": sorted(EXPECTED_TABLES)}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        connection.close()
    except sqlite3.Error as exc:
        return {"path": str(path), "compatible": False, "database_exists": True, "database_error": str(exc)}
    missing = sorted(EXPECTED_TABLES - tables)
    return {"path": str(path), "compatible": not missing, "database_exists": True, "missing_tables": missing}


def history_candidates(configured: Path) -> list[Path]:
    configured = configured.expanduser().resolve()
    candidates = [configured, configured.parent / "catalog-history.sqlite3"]
    for parent in list(configured.parents)[:4]:
        candidates.append(parent / "results" / "catalog-history.sqlite3")
    candidates.append(Path("results/catalog-history.sqlite3").resolve())
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def resolve_history(configured: Path) -> Path | None:
    configured = configured.expanduser().resolve()
    for candidate in history_candidates(configured):
        if probe_history(candidate).get("compatible"):
            return candidate
    return None


def main() -> int:
    from . import dashboard_service as dashboard
    from .live_dashboard import LIVE_PAGE, inject_live_discovery, live_product_state

    original_state = dashboard._history_state_sync
    original_inject = dashboard._inject_live_shell
    original_create_app = dashboard.create_dashboard_app

    def compatible_state(configured: Path) -> dict[str, Any]:
        configured = configured.expanduser().resolve()
        candidate = resolve_history(configured)
        if candidate is not None:
            state = original_state(candidate)
            state["configured_history_path"] = str(configured)
            state["history_path"] = str(candidate)
            state["auto_selected_history"] = candidate != configured
            state["schema_status"] = "live_history"
            if state.get("latest_run") is None:
                state["latest_run"] = {"status": "waiting_for_scanner"}
            try:
                live = live_product_state(candidate, limit=6)
                state.update({key: value for key, value in live.items() if key != "products"})
            except sqlite3.Error as exc:
                state["live_product_error"] = f"{type(exc).__name__}: {exc}"
            return state
        info = probe_history(configured)
        status = "misconfigured" if info.get("database_exists") else "disconnected"
        return {
            "database_exists": bool(info.get("database_exists")),
            "observations": 0,
            "active_listings": 0,
            "max_observation_id": 0,
            "latest_run": {"status": status},
            "recent": [],
            "scanner_status": status,
            "schema_status": "legacy_or_incompatible" if info.get("database_exists") else "missing",
            "missing_tables": info.get("missing_tables", []),
            "configured_history_path": str(configured),
            "history_path": None,
            "live_products": 0,
            "live_priced": 0,
            "live_stock_known": 0,
            "live_sources": 0,
        }

    def inject(html: str) -> str:
        return inject_live_discovery(original_inject(html))

    def create_app(**kwargs: Any) -> web.Application:
        app = original_create_app(**kwargs)

        async def live_products(request: web.Request) -> web.Response:
            try:
                limit = min(2000, max(1, int(request.query.get("limit", "200"))))
            except ValueError:
                limit = 200
            configured: Path = request.app["dashboard_history"]
            history = resolve_history(configured)
            if history is None:
                return web.json_response({
                    "live_products": 0,
                    "live_priced": 0,
                    "live_stock_known": 0,
                    "live_sources": 0,
                    "products": [],
                    "latest_run": {"status": "disconnected"},
                    "history_path": None,
                })
            try:
                payload = await asyncio.to_thread(live_product_state, history, limit=limit)
                state = request.app.get("dashboard_db_state") or await dashboard._history_state(history)
                payload["latest_run"] = state.get("latest_run")
                payload["history_path"] = str(history)
                return web.json_response(payload)
            except sqlite3.Error as exc:
                return web.json_response({"error": f"{type(exc).__name__}: {exc}", "products": []}, status=503)

        async def live_page(_: web.Request) -> web.Response:
            return web.Response(text=LIVE_PAGE, content_type="text/html", headers={"Cache-Control": "no-store"})

        app.router.add_get("/live", live_page)
        app.router.add_get("/api/live-products", live_products)
        return app

    dashboard._history_state_sync = compatible_state
    dashboard._inject_live_shell = inject
    dashboard.create_dashboard_app = create_app
    return dashboard.main()


if __name__ == "__main__":
    raise SystemExit(main())
