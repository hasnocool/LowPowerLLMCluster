from lowpower_llm_cluster.bios_versioning import compare_bios_versions, shipped_bios_meets_requirement


def test_msi_base36_suffix_order_handles_a9_to_ab():
    result=compare_bios_versions("7C56vAB","7C56vA9",manufacturer="msi")
    assert result["comparable"] is True
    assert result["relation"] == 1


def test_msi_different_board_prefix_is_not_comparable():
    result=compare_bios_versions("7C56vAB","7D00vA9",manufacturer="msi")
    assert result["comparable"] is False


def test_gigabyte_f12_to_f14():
    result=compare_bios_versions("F14","F12",manufacturer="gigabyte")
    assert result["relation"] == 1


def test_gigabyte_stable_release_sorts_after_same_number_beta():
    assert compare_bios_versions("F14","F14a",manufacturer="gigabyte")["relation"] == 1


def test_asus_numeric_versions_compare_numerically():
    assert compare_bios_versions("2802","2603",manufacturer="asus")["relation"] == 1


def test_asrock_only_compares_within_same_version_series():
    assert compare_bios_versions("P1.40","P1.20",manufacturer="asrock")["relation"] == 1
    assert compare_bios_versions("L3.01","P1.20",manufacturer="asrock")["comparable"] is False


def test_unknown_vendor_only_exact_match_is_safe():
    assert compare_bios_versions("AB","A9",manufacturer="generic")["comparable"] is False
    assert compare_bios_versions("A9","A9",manufacturer="generic")["relation"] == 0


def test_source_host_selects_vendor_comparator():
    result=shipped_bios_meets_requirement("F14","F12",source_url="https://www.gigabyte.com/Motherboard/example/support")
    assert result["meets_minimum"] is True
    assert result["manufacturer"] == "gigabyte"
