from lowpower_llm_cluster.catalog import load_catalog


def _parts() -> dict[str, dict]:
    return {part["id"]: part for part in load_catalog()["parts"]}


def test_current_genai_accelerators_require_demonstrated_transformer_runtime() -> None:
    parts = _parts()
    expected = {
        "accel-furiosa-rngd-48g": (48, "Furiosa-LLM"),
        "accel-tenstorrent-blackhole-p150-32g": (32, "tt-inference-server"),
        "accel-tenstorrent-wormhole-n300s-24g": (24, "tt-inference-server"),
    }
    for part_id, (memory_gb, runtime) in expected.items():
        part = parts[part_id]
        assert part["llm_candidate"] is True
        assert part["memory_capacity_gb"] == memory_gb
        assert part["demonstrated_transformer_runtime"] == runtime
        assert part["demonstrated_models"]
        assert part["source_url"].startswith("https://")
        assert part["power_scope"].startswith("accelerator_")


def test_furiosa_rngd_keeps_board_power_separate_from_host_power() -> None:
    part = _parts()["accel-furiosa-rngd-48g"]
    assert part["memory_type"] == "HBM3"
    assert part["memory_bandwidth_gbps"] == 1500
    assert part["power_target_w"] == 180
    assert part["power_scope"] == "accelerator_board_tdp"
    assert "complete-node" not in part.get("power_scope", "")


def test_blackhole_and_wormhole_memory_is_not_pooled_by_default() -> None:
    parts = _parts()
    assert parts["accel-tenstorrent-blackhole-p150-32g"]["memory_capacity_gb"] == 32
    assert parts["accel-tenstorrent-wormhole-n300s-24g"]["memory_capacity_gb"] == 24
    assert parts["accel-tenstorrent-blackhole-p150-32g"]["host_mode"] == "pcie_gen5_x16"
    assert parts["accel-tenstorrent-wormhole-n300s-24g"]["host_mode"] == "pcie_gen4_x16"


def test_large_memory_alveo_cards_remain_research_only() -> None:
    parts = _parts()
    for part_id in ("accel-amd-alveo-u200-64g-secondary", "accel-amd-alveo-u250-64g-secondary"):
        part = parts[part_id]
        assert part["category"] == "decommissioned_accelerator"
        assert part["memory_capacity_gb"] == 64
        assert part["llm_candidate"] is False
        assert part["llm_support"] == "research_only_custom_port_required"
        assert part["demonstrated_transformer_runtime"] is None
        assert part["price_status"] == "secondary_market_watch"
        assert "XRT" in part["software_stack"]


def test_no_current_genai_entry_uses_tops_as_llm_throughput() -> None:
    parts = _parts()
    for part_id in (
        "accel-furiosa-rngd-48g",
        "accel-tenstorrent-blackhole-p150-32g",
        "accel-tenstorrent-wormhole-n300s-24g",
    ):
        part = parts[part_id]
        for forbidden in ("tokens_per_second", "tokens_per_sec", "llm_tokens_per_second"):
            assert forbidden not in part
