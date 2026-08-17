from lowpower_llm_cluster.catalog import load_catalog


def _parts() -> dict[str, dict]:
    return {part["id"]: part for part in load_catalog()["parts"]}


def _discovery_ids() -> set[str]:
    return {
        "node-gmktec-k6-7840hs",
        "node-beelink-ser8-8845hs",
        "node-minisforum-um890pro-8945hs",
        "node-minisforum-ai-x1-pro-hx370",
        "sbc-radxa-rock5bp-32g",
        "sbc-radxa-rock4d-16g",
        "sbc-orange-pi5-32g",
    }


def test_ryzen_discovery_covers_requested_cpu_families() -> None:
    parts = _parts()
    expected = {
        "node-gmktec-k6-7840hs": ("AMD Ryzen 7 7840HS", 64),
        "node-beelink-ser8-8845hs": ("AMD Ryzen 7 8845HS", 256),
        "node-minisforum-um890pro-8945hs": ("AMD Ryzen 9 8945HS", 96),
        "node-minisforum-ai-x1-pro-hx370": ("AMD Ryzen AI 9 HX 370", 128),
    }
    for part_id, (cpu, max_memory_gb) in expected.items():
        part = parts[part_id]
        assert part["category"] == "mini_pc"
        assert part["cpu"] == cpu
        assert part["memory_config_status"] == "configurable"
        assert part["max_memory_gb"] == max_memory_gb
        assert part["source_url"].startswith("https://")
        assert "power_target_w" not in part


def test_hx370_uses_current_vendor_memory_limit() -> None:
    part = _parts()["node-minisforum-ai-x1-pro-hx370"]
    assert part["max_memory_gb"] == 128
    assert "128GB" in part["source_notes"]
    assert "vendor-stated maximum" in part["source_notes"]


def test_rockchip_expansion_adds_fixed_16_and_32gb_nodes() -> None:
    parts = _parts()
    expected = {
        "sbc-radxa-rock5bp-32g": ("Rockchip RK3588", 32),
        "sbc-radxa-rock4d-16g": ("Rockchip RK3576", 16),
        "sbc-orange-pi5-32g": ("Rockchip RK3588S", 32),
    }
    for part_id, (cpu, memory_gb) in expected.items():
        part = parts[part_id]
        assert part["category"] == "sbc"
        assert part["cpu"] == cpu
        assert part["memory_config_status"] == "fixed"
        assert part["memory_capacity_gb"] == memory_gb
        assert part["max_memory_gb"] == memory_gb
        assert part["software_maturity"].startswith("community_linux_rk")
        assert "power_target_w" not in part


def test_discovery_expansion_does_not_invent_benchmark_fields() -> None:
    parts = _parts()
    forbidden_fields = {
        "tokens_per_second",
        "prompt_tokens_per_second",
        "generation_tokens_per_second",
        "benchmark_tps",
        "measured_tps",
        "llm_throughput",
        "inference_power_w",
        "inference_wall_power_w",
    }
    for part_id in _discovery_ids():
        part = parts[part_id]
        assert forbidden_fields.isdisjoint(part)
        assert "power_target_w" not in part
