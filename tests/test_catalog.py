# tests/test_catalog.py
from lowpower_llm_cluster.catalog import llm_candidates, load_catalog, midpoint_price
from lowpower_llm_cluster.scoring import node_score


def test_catalog_has_parts() -> None:
    assert load_catalog()["parts"]


def test_known_prices_are_ordered_and_unknown_prices_are_paired() -> None:
    for part in load_catalog()["parts"]:
        low = part["price_min_usd"]
        high = part["price_max_usd"]
        assert (low is None) == (high is None)
        if low is not None:
            assert low <= high
            assert midpoint_price(part) is not None
            assert midpoint_price(part) > 0
        else:
            assert midpoint_price(part) is None


def test_llm_candidates_with_prices_get_screening_scores() -> None:
    candidates = llm_candidates(load_catalog()["parts"])
    assert candidates
    priced = [node for node in candidates if midpoint_price(node) is not None]
    assert priced
    assert all(node_score(node) > 0 for node in priced)


def test_catalog_includes_multiple_hardware_classes() -> None:
    classes = {p.get("hardware_class") for p in load_catalog()["parts"] if p.get("hardware_class")}
    assert {"mini_pc", "edge_ai_developer_kit", "rk3588_sbc", "salvaged_accelerated_apu_board"} <= classes


def test_catalog_includes_accelerator_families() -> None:
    families = {p.get("accelerator_family") for p in load_catalog()["parts"] if p.get("accelerator_family")}
    assert {"npu", "tpu", "ai_asic", "adaptive_soc_fpga"} <= families


def test_fixed_function_accelerators_are_not_mislabeled_as_llm_nodes() -> None:
    by_id = {p["id"]: p for p in load_catalog()["parts"]}
    assert by_id["accel-google-coral-usb"]["llm_candidate"] is False
    assert by_id["accel-memryx-mx3-m2"]["llm_candidate"] is False
    assert by_id["accel-rpi-ai-hat2-hailo10h"]["llm_candidate"] is True
