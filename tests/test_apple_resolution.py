from lowpower_llm_cluster.apple_resolution import resolve_apple_configuration


def test_m1_max_marketplace_listing_resolves_without_inventing_gpu():
    config = resolve_apple_configuration(
        "Apple MacBook Pro A2485 M1 Max 64GB 2TB SSD 16-inch",
        "Battery health 91%, cycle count 183, Find My off, no MDM",
    )
    assert config["apple_a_number"] == "A2485"
    assert config["soc"] == "Apple M1 Max"
    assert config["memory_capacity_gb"] == 64
    assert config["storage_gb"] == 2000
    assert config["screen_inches"] == 16.2
    assert "gpu_cores" not in config
    assert config["condition_evidence"]["battery_cycle_count"] == 183
    assert config["condition_evidence"]["battery_health_percent"] == 91
    assert config["condition_evidence"]["activation_lock"] is False
    assert config["condition_evidence"]["mdm_enrollment"] is False
    assert config["apple_resolution"]["exact_configuration"] is True
    assert config["apple_resolution"]["gpu_core_count_explicit"] is False


def test_explicit_gpu_core_count_is_preserved():
    config = resolve_apple_configuration("MacBook Pro A2442 M1 Max 10-core CPU 32-core GPU 64GB RAM 1TB SSD 14-inch")
    assert config["cpu_cores"] == 10
    assert config["gpu_cores"] == 32
    assert config["screen_inches"] == 14.2


def test_conflicting_existing_evidence_blocks_exact_label():
    config = resolve_apple_configuration(
        "MacBook Pro A2485 M1 Max 64GB RAM 2TB SSD",
        existing={"memory_capacity_gb": 32},
    )
    assert "memory_capacity_gb" in config["apple_resolution"]["conflicts"]
    assert config["apple_resolution"]["exact_configuration"] is False


def test_non_apple_listing_is_unchanged():
    original = {"memory_capacity_gb": 32}
    assert resolve_apple_configuration("Ryzen mini PC 32GB 1TB", existing=original) == original
