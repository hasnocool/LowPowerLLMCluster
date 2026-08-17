from lowpower_llm_cluster.mobile_platform import mobile_runtime_profile, model_fit_memory_budget


def test_mac_is_general_purpose_metal_node():
    part = {"category": "apple_silicon_system", "name": "Mac mini", "memory_capacity_gb": 32, "software_stack": "macOS; Metal; MLX; Core ML"}
    profile = mobile_runtime_profile(part)
    assert profile["headless_service"] is True
    assert profile["mlx"] is True
    assert model_fit_memory_budget(part)["usable_gb"] == 24.0


def test_phone_is_not_ranked_as_daemon_host():
    part = {"category": "mobile_phone", "name": "iPhone", "memory_capacity_gb": None, "software_stack": "iOS; Metal; Core ML"}
    profile = mobile_runtime_profile(part)
    assert profile["persistent_daemon"] is False
    assert profile["local_cli"] is False
    assert model_fit_memory_budget(part)["known"] is False


def test_tablet_uses_larger_memory_reserve():
    part = {"category": "tablet", "name": "iPad Pro", "memory_capacity_gb": 16, "software_stack": "iPadOS; Metal; Core ML"}
    budget = model_fit_memory_budget(part)
    assert budget["usable_gb"] == 9.6
    assert budget["performance_claim"] is False


def test_android_phone_exposes_local_cli_path_without_becoming_daemon_host():
    part = {
        "category": "mobile_phone",
        "name": "OnePlus 15",
        "memory_capacity_gb": 16,
        "software_stack": "OxygenOS 16 based on Android 16; Vulkan; Android native/app-local inference runtimes",
    }
    profile = mobile_runtime_profile(part)
    assert profile["local_cli"] is True
    assert profile["vulkan"] is True
    assert profile["headless_service"] is False
    assert profile["persistent_daemon"] is False
    assert model_fit_memory_budget(part)["usable_gb"] == 9.6


def test_android_tablet_uses_mobile_constraints_with_cli_path():
    part = {
        "category": "tablet",
        "name": "Galaxy Tab S11 Ultra",
        "memory_capacity_gb": 16,
        "software_stack": "Android 16 / One UI 8; Vulkan; Android native/app-local inference runtimes",
    }
    profile = mobile_runtime_profile(part)
    assert profile["local_cli"] is True
    assert profile["vulkan"] is True
    assert profile["thermal_constraint"] == "medium_high"
    assert profile["persistent_daemon"] is False
