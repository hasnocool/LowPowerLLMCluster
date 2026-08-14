from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from lowpower_llm_cluster.active_records import active_records
from lowpower_llm_cluster.canonical_promotion import evaluate, promote
from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.history_compaction import CompactingCatalogHistory
from lowpower_llm_cluster.manufacturer_identity import enrich_identity
from lowpower_llm_cluster.promotion_state import project_promotion_records
from lowpower_llm_cluster.resilient_runtime import ResilientAsyncHttpClient
from lowpower_llm_cluster.source_cooldown import SourceCooldownStore
from lowpower_llm_cluster.source_failures import classify_error


def record(**overrides):
    value = {
        "source": "radxa-products-public",
        "source_id": "rock-5",
        "listing_url": "https://radxa.com/products/rock5/5b",
        "title": "ROCK 5B",
        "manufacturer": "Radxa",
        "sku": "ROCK-5B",
        "mpn": "ROCK-5B",
        "source_confidence": 0.95,
        "sku_confidence": 0.9,
        "in_stock": True,
        "observed_at": "2026-08-14T01:00:00+00:00",
        "raw_attributes": {},
    }
    value.update(overrides)
    return value


def test_failure_classes_match_log_patterns() -> None:
    assert classify_error("ClientResponseError: 403 Forbidden").failure_class == "access_denied"
    assert classify_error("429 Too Many Requests").failure_class == "rate_limited"
    assert classify_error("certificate verify failed").failure_class == "tls_error"
    assert classify_error("ClientConnectorError: Cannot connect to host").failure_class == "network_error"
    assert classify_error("500 Internal Server Error").failure_class == "server_error"
    assert classify_error("Got more than 8190 bytes when reading Header value").failure_class == "protocol_error"


def test_official_source_enrichment_can_supply_manufacturer_and_url_identity() -> None:
    enriched = enrich_identity(record(manufacturer="", sku="", mpn="", sku_confidence=0.1), {"name":"radxa-products-public","source_class":"manufacturer","seeds":["https://radxa.com/products"]})
    assert enriched["manufacturer"] == "Radxa"
    assert enriched["raw_attributes"]["official_product_url_identity"] is True
    assert "identity_confidence_below_threshold" not in evaluate(enriched)


def test_metadata_fallback_remains_held_until_structured_enrichment() -> None:
    base = record(raw_attributes={"metadata_fallback": True})
    assert "metadata_fallback_unverified" in evaluate(base)
    enriched = record(raw_attributes={"metadata_fallback": False, "structured_product_enriched": True})
    assert "metadata_fallback_unverified" not in evaluate(enriched)


def test_promotion_report_persists_decisions_and_exact_listing_provenance(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"; report = tmp_path / "report.json"
    promoted = record(source="official", source_id="official-1")
    result = promote([promoted], catalog_path=catalog, report_path=report)
    assert result["decisions"][0]["state"] == "canonical"
    catalog_payload = json.loads(catalog.read_text())
    report_payload = json.loads(report.read_text())
    seller = record(source="seller", source_id="seller-1", source_confidence=0.4)
    projected = project_promotion_records([seller], report=report_payload, catalog=catalog_payload)
    assert projected["items"][0]["promotion_state"] != "canonical"


def test_persisted_decision_survives_later_projection() -> None:
    row = record(observed_at="2026-08-14T00:00:00+00:00", source_confidence=0.4)
    report = {"generated_at":"2026-08-14T00:30:00+00:00","decisions":[{"source":"radxa-products-public","source_id":"rock-5","state":"held","reasons":["source_confidence_below_threshold"],"canonical_id":None}]}
    projected = project_promotion_records([row], report=report, catalog={"parts":[]})
    assert projected["items"][0]["promotion_state"] == "held"
    assert projected["items"][0]["promotion_reasons"] == ["source_confidence_below_threshold"]


def test_resilient_http_header_limits_are_bounded() -> None:
    client = ResilientAsyncHttpClient(max_line_size=10**9, max_field_size=10**9)
    assert client.max_line_size == 131072
    assert client.max_field_size == 131072


def test_source_cooldown_backs_off_and_success_resets(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    store = SourceCooldownStore(path)
    asyncio.run(store.initialize())
    asyncio.run(store.record_cycle(cycle_index=1, selected_sources=["blocked"], errors={"blocked":"403 Forbidden"}))
    first = asyncio.run(store.policies(["blocked"]))["blocked"]
    assert first["failure_class"] == "access_denied" and first["cooldown_until_cycle"] >= 17
    asyncio.run(store.record_cycle(cycle_index=20, selected_sources=["blocked"], errors={}))
    reset = asyncio.run(store.policies(["blocked"]))["blocked"]
    assert reset["consecutive_failures"] == 0 and reset["cooldown_until_cycle"] == 0


def test_source_cooldown_cycle_epoch_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    first = SourceCooldownStore(path)
    asyncio.run(first.initialize())
    assert asyncio.run(first.next_cycle_index()) == 1
    assert asyncio.run(first.next_cycle_index()) == 2
    asyncio.run(first.record_cycle(cycle_index=2, selected_sources=["blocked"], errors={"blocked":"403 Forbidden"}))
    deadline = asyncio.run(first.policies(["blocked"]))["blocked"]["cooldown_until_cycle"]

    restarted = SourceCooldownStore(path)
    asyncio.run(restarted.initialize())
    assert asyncio.run(restarted.current_cycle_index()) == 2
    next_cycle = asyncio.run(restarted.next_cycle_index())
    assert next_cycle == 3
    assert deadline - next_cycle <= 15


def test_compacting_history_keeps_state_but_samples_unchanged_rows(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    history = CompactingCatalogHistory(path, unchanged_heartbeat_s=3600)
    async def run():
        await history.initialize()
        one = ProductObservation(source="shop", source_id="sku", listing_url="https://example.test/p", title="Part", price=1.0, observed_at="2026-08-14T00:00:00+00:00")
        two = ProductObservation(source="shop", source_id="sku", listing_url="https://example.test/p", title="Part", price=1.0, observed_at="2026-08-14T00:05:00+00:00")
        await history.record_refresh([one]); await history.record_refresh([two]); await history.close()
    asyncio.run(run())
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert con.execute("SELECT last_seen_at FROM listing_state").fetchone()[0] == "2026-08-14T00:05:00+00:00"
    con.close()


def test_compacting_history_preserves_payload_only_evidence_changes(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    history = CompactingCatalogHistory(path, unchanged_heartbeat_s=3600)

    async def run():
        await history.initialize()
        one = ProductObservation(
            source="shop", source_id="sku", listing_url="https://example.test/p", title="Part", price=1.0,
            manufacturer="", sku="", attributes={"metadata_fallback": True},
            observed_at="2026-08-14T00:00:00+00:00",
        )
        two = ProductObservation(
            source="shop", source_id="sku", listing_url="https://example.test/p", title="Part", price=1.0,
            manufacturer="Example Vendor", sku="ABC-123", attributes={"structured_product_enriched": True},
            observed_at="2026-08-14T00:05:00+00:00",
        )
        await history.record_refresh([one]); await history.record_refresh([two]); await history.close()

    asyncio.run(run())
    con = sqlite3.connect(path)
    rows = con.execute("SELECT payload_json FROM observations ORDER BY id").fetchall()
    con.close()
    assert len(rows) == 2
    latest = json.loads(rows[-1][0])
    assert latest["manufacturer"] == "Example Vendor"
    assert latest["sku"] == "ABC-123"
    assert latest["attributes"]["structured_product_enriched"] is True


def test_active_records_returns_more_than_ten_thousand(tmp_path: Path) -> None:
    path = tmp_path / "large.sqlite3"; con = sqlite3.connect(path)
    con.executescript("CREATE TABLE refresh_runs(run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, status TEXT); CREATE TABLE observations(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, source TEXT, source_id TEXT, observed_at TEXT, listing_url TEXT, title TEXT, price REAL, currency TEXT, shipping REAL, in_stock INTEGER, payload_json TEXT); CREATE TABLE listing_state(source TEXT, source_id TEXT, listing_url TEXT, title TEXT, price REAL, currency TEXT, in_stock INTEGER, last_seen_at TEXT, missing_runs INTEGER, disappeared INTEGER, PRIMARY KEY(source,source_id));")
    rows = [("bulk", f"id-{i}", f"https://example.test/{i}", f"Part {i}", None, "USD", 1, "2026-08-14T00:00:00Z", 0, 0) for i in range(10001)]
    con.executemany("INSERT INTO listing_state VALUES (?,?,?,?,?,?,?,?,?,?)", rows); con.commit(); con.close()
    result = asyncio.run(active_records(path))
    assert result["total"] == 10001 and len(result["items"]) == 10001
