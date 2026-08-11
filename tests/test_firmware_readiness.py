from lowpower_llm_cluster.firmware_readiness import boot_readiness_score, detect_bios_flashback, discover_support_endpoints


def test_support_endpoint_discovery_stays_on_official_host():
    html = '''
    <a href="/support/cpu-support">CPU Support List</a>
    <a href="/support/bios-downloads">BIOS Downloads</a>
    <a href="https://evil.example/bios">BIOS mirror</a>
    '''
    rows = discover_support_endpoints(html, "https://vendor.example/board", {"vendor.example"})
    assert len(rows) == 2
    assert rows[0]["url"].startswith("https://vendor.example/")
    assert all("evil.example" not in row["url"] for row in rows)


def test_flashback_detection_requires_explicit_cpu_less_language_for_high_confidence():
    result = detect_bios_flashback("USB BIOS FlashBack lets you update BIOS without installing a CPU or memory.")
    assert result["status"] == "supported"
    assert result["cpu_less_update_explicit"] is True
    assert result["confidence"] == "high"


def test_supported_cpu_with_minimum_bios_and_cpu_less_recovery_scores_high():
    cpu_bios = {"status": "supported", "minimum_bios_version": "7C56vA9", "matrix_complete": True}
    flashback = {"status": "supported", "cpu_less_update_explicit": True}
    result = boot_readiness_score(cpu_bios, flashback)
    assert result["score"] == 88
    assert "cpu_less_recovery_available" in result["readiness"]


def test_explicit_factory_bios_equal_to_minimum_proves_readiness():
    flashback = detect_bios_flashback("This board ships with BIOS version A9 from factory.")
    result = boot_readiness_score({"status": "supported", "minimum_bios_version": "A9", "matrix_complete": True}, flashback)
    assert flashback["shipped_bios_version"] == "A9"
    assert result["score"] == 98
    assert result["shipped_bios_meets_minimum"] is True
    assert result["readiness"] == "ready_with_verified_firmware"


def test_different_factory_bios_version_is_not_ordered_without_vendor_comparator():
    flashback = detect_bios_flashback("This board ships with BIOS version AB from factory.")
    result = boot_readiness_score({"status": "supported", "minimum_bios_version": "A9", "matrix_complete": True}, flashback)
    assert result["shipped_bios_meets_minimum"] is None
    assert any("version ordering" in warning for warning in result["warnings"])


def test_manufacture_date_does_not_create_shipped_bios_evidence():
    flashback = detect_bios_flashback("Manufactured 2025-08. Latest BIOS is AB.")
    assert flashback["shipped_bios_version"] is None


def test_unsupported_cpu_is_zero_readiness():
    result = boot_readiness_score({"status": "unsupported", "minimum_bios_version": None}, {"status": "supported", "cpu_less_update_explicit": True})
    assert result["score"] == 0
    assert result["readiness"] == "not_bootable_with_selected_cpu"


def test_unresolved_incomplete_matrix_never_becomes_false_unsupported():
    result = boot_readiness_score({"status": "unresolved", "reason": "not found", "matrix_complete": False}, {"status": "unknown"})
    assert result["score"] == 34
    assert result["cpu_bios_status"] == "unresolved"
    assert any("not proven complete" in warning for warning in result["warnings"])
