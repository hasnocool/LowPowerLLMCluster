from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from lowpower_llm_cluster.ops import stale_listings, with_retry


def test_retry_recovers_from_transient_http_error():
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("temporary", request=request, response=response)
        return "ok"

    assert asyncio.run(with_retry(flaky, attempts=3, base_delay_s=0.001, max_delay_s=0.001)) == "ok"
    assert attempts == 3


def test_retry_does_not_repeat_non_transient_http_error():
    attempts = 0

    async def bad_request():
        nonlocal attempts
        attempts += 1
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("bad", request=request, response=response)

    try:
        asyncio.run(with_retry(bad_request, attempts=4, base_delay_s=0.001))
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
    assert attempts == 1


def test_stale_warning_only_flags_active_old_listings(tmp_path: Path):
    now = datetime.now(UTC)
    payload = {
        "schema_version": 1,
        "states": {
            "old": {"source": "fixture", "source_id": "1", "title": "old active", "active": True, "last_seen": (now - timedelta(hours=80)).isoformat()},
            "fresh": {"source": "fixture", "source_id": "2", "title": "fresh active", "active": True, "last_seen": (now - timedelta(hours=2)).isoformat()},
            "gone": {"source": "fixture", "source_id": "3", "title": "old gone", "active": False, "last_seen": (now - timedelta(hours=100)).isoformat()}
        },
        "events": []
    }
    path = tmp_path / "listing-state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rows = stale_listings(stale_after_hours=72, path=path)
    assert [row["title"] for row in rows] == ["old active"]
