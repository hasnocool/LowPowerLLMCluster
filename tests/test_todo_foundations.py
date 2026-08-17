# tests/test_todo_foundations.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from lowpower_llm_cluster.landed_history import (
    LandedCostHistory,
    TariffEvidence,
    fx_only_delta,
    make_landed_snapshot,
)
from lowpower_llm_cluster.notifications import deliver_alerts
from lowpower_llm_cluster.owned_host import validate_owned_host
from lowpower_llm_cluster.pricing import FxTable
from lowpower_llm_cluster.quota import ProviderQuotaHistory, parse_provider_quota


def _gpu() -> dict:
    return {
        "id": "rtx-test",
        "category": "gpu_accelerator",
        "host_requirements": "PCIe 4.0 x16 host; 750W required system power.",
        "length_mm": 310,
        "slot_width": 3,
        "power_connectors": ["8-pin", "8-pin"],
        "default_tgp_w": 350,
    }


def _owned_host() -> dict:
    return {
        "pcie_slots": [{"id": "slot-1", "physical": "x16", "lanes": 16, "generation": 4, "available": True}],
        "psu_wattage_w": 850,
        "estimated_peak_system_w": 700,
        "psu_gpu_power_connectors": ["8-pin", "8-pin", "8-pin"],
        "chassis_max_gpu_length_mm": 340,
        "chassis_max_gpu_slots": 4,
        "gpu_cooling_capacity_w": 400,
    }


def test_owned_host_validation_covers_slot_power_connectors_clearance_and_cooling() -> None:
    result = validate_owned_host(_gpu(), _owned_host())
    assert result.status == "compatible"
    assert result.selected_pcie_slot is not None
    assert result.selected_pcie_slot["id"] == "slot-1"
    assert result.cooling_power_basis == "catalog_board_power"
    assert not result.failures
    assert not result.unknowns


def test_owned_host_rejects_insufficient_lane_wiring_and_duplicate_connector_count() -> None:
    host = _owned_host()
    host["pcie_slots"][0]["lanes"] = 8
    host["psu_gpu_power_connectors"] = ["8-pin"]
    result = validate_owned_host(_gpu(), host)
    assert result.status == "incompatible"
    assert any("pcie_lanes" in failure for failure in result.failures)
    assert any("gpu_power_connectors" in failure for failure in result.failures)


def test_owned_host_missing_facts_stays_provisional() -> None:
    result = validate_owned_host(_gpu(), {"pcie_gpu_slot_present": True, "psu_wattage_w": 850})
    assert result.status == "provisionally_compatible"
    assert "pcie_lanes" in result.unknowns
    assert "psu_headroom" in result.unknowns
    assert "gpu_clearance" in result.unknowns


def test_landed_history_preserves_fx_and_tariff_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        tariff = TariffEvidence(
            hs_code="8471.50",
            duty_rate=0.05,
            source_url="https://example.test/tariff",
            verified_on="2026-08-17",
            origin_country="US",
            description="fixture tariff evidence",
        )
        first = make_landed_snapshot(
            source="fixture",
            source_id="item-1",
            listing_url="https://example.test/item-1",
            listing_observed_at="2026-08-17T10:00:00+00:00",
            item_price=100,
            source_currency="USD",
            shipping=10,
            fx=FxTable(target_currency="CAD", rates={"USD": 1.30}, as_of="2026-08-17"),
            tariff=tariff,
        )
        second = make_landed_snapshot(
            source="fixture",
            source_id="item-1",
            listing_url="https://example.test/item-1",
            listing_observed_at="2026-08-18T10:00:00+00:00",
            item_price=100,
            source_currency="USD",
            shipping=10,
            fx=FxTable(target_currency="CAD", rates={"USD": 1.40}, as_of="2026-08-18"),
            tariff=tariff,
        )
        history = LandedCostHistory(tmp_path / "landed.json")
        assert await history.append(first) is True
        assert await history.append(first) is False
        assert await history.append(second) is True
        rows = await history.snapshots(source="fixture", source_id="item-1")
        assert len(rows) == 2
        assert rows[0]["fx_rates"]["USD"] == 1.30
        assert rows[0]["tariff_evidence"]["hs_code"] == "8471.50"
        delta = fx_only_delta(rows[0], rows[1])
        assert delta["delta_cad"] > 0
        assert delta["first_fx_as_of"] == "2026-08-17"

    asyncio.run(scenario())


def test_fx_only_delta_rejects_native_price_change() -> None:
    base = {
        "source": "fixture",
        "source_id": "1",
        "item_price": 100.0,
        "source_currency": "USD",
        "shipping": 0.0,
        "shipping_currency": "USD",
        "brokerage_cad": 0.0,
        "province": "BC",
        "province_tax_rate": 0.12,
        "tariff_evidence": None,
        "fx_as_of": "a",
        "estimate": {"total_cad": 140.0},
    }
    changed = {**base, "item_price": 101.0, "fx_as_of": "b", "estimate": {"total_cad": 145.0}}
    with pytest.raises(ValueError, match="item_price"):
        fx_only_delta(base, changed)


def test_provider_quota_parser_preserves_remaining_limit_and_reset() -> None:
    snapshot = parse_provider_quota(
        "github-like",
        {
            "X-RateLimit-Remaining": "42",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1786992000",
        },
        observed_at="2026-08-17T12:00:00+00:00",
    )
    assert snapshot is not None
    assert snapshot.remaining == 42
    assert snapshot.limit == 5000
    assert snapshot.reset_at is not None
    assert "x-ratelimit-remaining" in snapshot.header_names
    assert parse_provider_quota("none", {"Content-Type": "application/json"}) is None


def test_provider_quota_history_is_async_and_restart_safe(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "quotas.json"
        history = ProviderQuotaHistory(path)
        await history.observe("fixture", {"RateLimit-Remaining": "9", "RateLimit-Limit": "10", "RateLimit-Reset-After": "60"})
        latest = await history.latest("fixture")
        assert latest["remaining"] == 9
        assert latest["reset_after_s"] == 60
        reopened = ProviderQuotaHistory(path)
        assert (await reopened.latest("fixture"))["limit"] == 10
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert len(payload["history"]) == 1

    asyncio.run(scenario())


class _RecordingAdapter:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.alerts: list[dict] = []

    async def send(self, alert) -> None:
        await asyncio.sleep(0)
        self.alerts.append(dict(alert))
        if self.fail:
            raise RuntimeError("fixture failure")


def test_notification_delivery_fans_out_and_isolates_adapter_failures() -> None:
    async def scenario() -> None:
        good = _RecordingAdapter("good")
        bad = _RecordingAdapter("bad", fail=True)
        alerts = [
            {"fingerprint": "a", "priority": "P2", "type": "price_drop", "title": "GPU", "reason": "20% lower"},
            {"fingerprint": "b", "priority": "P4", "type": "new_product", "title": "SBC", "reason": "new"},
        ]
        deliveries = await deliver_alerts(alerts, [good, bad], maximum_priority="P2")
        assert len(deliveries) == 2
        assert len(good.alerts) == 1
        assert good.alerts[0]["fingerprint"] == "a"
        assert any(delivery.ok for delivery in deliveries)
        assert any(not delivery.ok and "fixture failure" in str(delivery.error) for delivery in deliveries)

    asyncio.run(scenario())
