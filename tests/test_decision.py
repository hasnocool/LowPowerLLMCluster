from __future__ import annotations

from datetime import UTC, datetime

from lowpower_llm_cluster.decision import evaluate_candidate, model_fit_summary, price_statistics, prioritize_alerts


def _part(**overrides):
    value = {
        "id": "gpu-test-16g",
        "name": "Test GPU 16GB",
        "category": "gpu_accelerator",
        "hardware_class": "discrete_gpu",
        "llm_candidate": True,
        "memory_capacity_gb": 16,
        "memory_config_status": "fixed",
        "software_maturity": "high",
        "risk_level": "low",
        "power_target_w": 180,
        "power_scope": "accelerator_board_tgp",
    }
    value.update(overrides)
    return value


def _row(price: float, when: str, **overrides):
    value = {
        "part_id": "gpu-test-16g",
        "source": "fixture-market",
        "source_id": "listing-1",
        "title": "Test GPU 16GB",
        "price": price,
        "currency": "USD",
        "shipping": 0.0,
        "shipping_currency": "USD",
        "observed_at": when,
        "source_kind": "structured_marketplace",
        "configuration_confidence": {"score": 0.95, "label": "exact"},
        "seller_confidence": {"score": 0.90, "label": "high"},
    }
    value.update(overrides)
    return value


def _state(last_seen: str = "2026-08-10T11:00:00+00:00"):
    return {
        "states": {
            "fixture": {
                "source": "fixture-market",
                "source_id": "listing-1",
                "title": "Test GPU 16GB",
                "active": True,
                "last_seen": last_seen,
            }
        },
        "events": [],
    }


def test_gpu_vram_capacity_screen_fits_14b_not_32b():
    result = model_fit_summary(_part())
    assert result["largest_fit"] == "14B Q4"
    assert result["fit_score"] == 0.5
    assert result["memory_basis"] == "fixed"


def test_price_history_detects_new_native_currency_all_time_low():
    rows = [
        _row(100.0, "2026-08-08T11:00:00+00:00"),
        _row(90.0, "2026-08-09T11:00:00+00:00"),
        _row(70.0, "2026-08-10T11:00:00+00:00"),
    ]
    result = price_statistics("gpu-test-16g", rows, _state(), {"USD": 1.30, "CAD": 1.0})
    assert result["new_all_time_low"] is True
    assert result["native_all_time_low"] == 70.0
    assert result["current_cad"] == 101.92
    assert result["trend_pct"] < 0
    assert result["volatility_pct"] > 0


def test_strong_fresh_all_time_low_can_be_buy_without_fake_throughput():
    rows = [
        _row(100.0, "2026-08-08T11:00:00+00:00"),
        _row(90.0, "2026-08-09T11:00:00+00:00"),
        _row(70.0, "2026-08-10T11:00:00+00:00"),
    ]
    result = evaluate_candidate(
        _part(),
        rows,
        _state(),
        {"USD": 1.30, "CAD": 1.0},
        now=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )
    assert result["recommendation"] == "Buy"
    assert result["deal_score"] >= 72
    assert result["model_fit"]["largest_fit"] == "14B Q4"
    assert "tokens" not in " ".join(result["reasons"]).casefold()


def test_old_marketplace_observation_expires_internally_without_claiming_sold():
    rows = [_row(70.0, "2026-08-07T11:00:00+00:00")]
    result = evaluate_candidate(
        _part(),
        rows,
        _state("2026-08-07T11:00:00+00:00"),
        {"USD": 1.30, "CAD": 1.0},
        now=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )
    assert result["opportunity"]["expired"] is True
    assert result["opportunity"]["basis"].startswith("listing freshness TTL")
    assert result["recommendation"] != "Buy"


def test_alert_priority_promotes_all_time_low_buy_candidate():
    recommendation = {
        "id": "gpu-test-16g",
        "recommendation": "Buy",
        "market_confidence": 0.9,
        "opportunity": {"expires_in_hours": 12.0},
    }
    alerts = [{"type": "all_time_low", "severity": "high", "part_id": "gpu-test-16g", "title": "Test GPU 16GB"}]
    result = prioritize_alerts(alerts, [recommendation])
    assert result[0]["priority"] == "P1"
    assert result[0]["priority_score"] >= 75
