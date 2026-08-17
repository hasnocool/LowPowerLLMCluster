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


def test_authoritative_m1_air_part_number_resolves_model_and_chip():
    config = resolve_apple_configuration("Apple MacBook Air MGN63LL/A 8GB RAM 256GB SSD")
    assert config["apple_part_number"] == "MGN63LL/A"
    assert config["apple_a_number"] == "A2337"
    assert config["model_identifier"] == "MacBookAir10,1"
    assert config["soc"] == "Apple M1"
    assert config["screen_inches"] == 13.3
    assert config["apple_resolution"]["exact_configuration"] is True
    assert config["apple_resolution"]["identifier_authority"] == "apple_support"
    evidence = config["apple_identifier_evidence"][0]
    assert evidence["record_id"] == "macbook-air-m1-2020"
    assert evidence["match_types"] == ["part_number"]


def test_authoritative_m2_air_part_number_resolves_current_mac_identifier():
    config = resolve_apple_configuration("MacBook Air MLXW3LL/A 16GB RAM 512GB SSD")
    assert config["apple_a_number"] == "A2681"
    assert config["model_identifier"] == "Mac14,2"
    assert config["soc"] == "Apple M2"
    assert config["screen_inches"] == 13.6
    assert config["apple_resolution"]["exact_configuration"] is True


def test_modern_mac_identifier_is_recognized_and_enriched():
    config = resolve_apple_configuration("MacBook Air Mac16,12 24GB RAM 1TB SSD")
    assert config["model_identifier"] == "Mac16,12"
    assert config["soc"] == "Apple M4"
    assert config["introduced_year"] == 2025
    assert config["screen_inches"] == 13.6


def test_pro_max_part_family_does_not_invent_chip_variant():
    config = resolve_apple_configuration("MacBook Pro MKGR3LL/A 32GB RAM 1TB SSD")
    assert config["product_family"] == "MacBook Pro"
    assert config["introduced_year"] == 2021
    assert config["screen_inches"] == 14.2
    assert config["soc_candidates"] == ["Apple M1 Pro", "Apple M1 Max"]
    assert "soc" not in config
    assert config["apple_resolution"]["exact_configuration"] is False
    assert config["apple_resolution"]["required_evidence"]["chip"] is False


def test_part_number_and_conflicting_seller_chip_blocks_exact_resolution():
    config = resolve_apple_configuration("MacBook Air MGN63LL/A M2 8GB RAM 256GB SSD")
    assert config["soc"] == "Apple M2"
    assert "soc" in config["apple_resolution"]["conflicts"]
    assert config["apple_resolution"]["exact_configuration"] is False


def test_mac_studio_part_number_can_establish_exact_chip_family():
    config = resolve_apple_configuration("Mac Studio MJMV2LL/A 64GB RAM 2TB SSD")
    assert config["model_identifier"] == "Mac13,1"
    assert config["soc"] == "Apple M1 Max"
    assert config["introduced_year"] == 2022
    assert config["apple_resolution"]["exact_configuration"] is True
