from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.catalog import project_root


ROOT = project_root()


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_secondary_accelerator_policy_has_expected_watches() -> None:
    payload = _json("data/market/secondary-accelerator-policy.json")
    watches = payload["watches"]
    expected = {
        "alveo-u200-64g",
        "alveo-u250-64g",
        "alveo-u55c-16g",
        "tenstorrent-n150-12g",
        "tenstorrent-n300-24g",
        "intel-gaudi-32g",
        "intel-gaudi2-96g",
        "amd-instinct-mi60-32g",
        "nvidia-a40-48g",
    }
    ids = {watch["id"] for watch in watches}
    assert ids == expected
    assert len(ids) == len(watches)
    valid_categories = {"gpu_accelerator", "ai_asic_accelerator", "fpga_accelerator", "decommissioned_accelerator"}
    for watch in watches:
        assert watch["category"] in valid_categories
        assert watch["max_landed_cad"] > 0
        assert watch["transformer_runtime_required"] is True
        assert watch["runtime_aliases"]
        assert watch["keywords"]


def test_secondary_accelerator_scan_profile_is_bounded_for_four_daily_runs() -> None:
    profiles = _json("data/market/profiles.json")["profiles"]
    profile = profiles["secondary-accelerator-scan"]
    assert set(profile["sources"]) == {"ebay", "manufacturer"}
    assert profile["refresh_fx"] is True
    required_queries = {
        "AMD Alveo U200 64GB",
        "AMD Alveo U250 64GB",
        "AMD Alveo U55C 16GB",
        "Tenstorrent Wormhole n150",
        "Tenstorrent Wormhole n300",
        "Habana Gaudi 32GB",
        "Intel Gaudi2 96GB",
        "AMD Instinct MI60 32GB",
        "NVIDIA A40 48GB",
    }
    assert required_queries <= set(profile["queries"])
    for budget in profile["source_budgets"].values():
        assert budget["daily_request_budget"] >= budget["max_queries_per_run"] * 4


def test_secondary_accelerator_watchlist_is_separate_from_generic_accelerators() -> None:
    watches = _json("data/market/watchlists.json")["watchlists"]
    watch = next(item for item in watches if item["id"] == "secondary-accelerator-value")
    assert watch["enabled"] is True
    assert "ai_asic_accelerator" in watch["match"]["categories"]
    assert "fpga_accelerator" in watch["match"]["categories"]
    text = " ".join(watch["match"]["keywords"]).casefold()
    for needle in ("alveo u200", "alveo u250", "alveo u55c", "wormhole n300", "gaudi2", "instinct mi60", "nvidia a40"):
        assert needle in text


def test_autonomous_refresh_schedules_secondary_accelerator_scan_four_times_daily() -> None:
    workflow = (ROOT / ".github/workflows/autonomous-refresh.yml").read_text(encoding="utf-8")
    assert "- secondary-accelerator-scan" in workflow
    assert 'cron: "23 4,10,16,22 * * *"' in workflow
    assert 'name=secondary-accelerator-scan' in workflow
