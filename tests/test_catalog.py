# tests/test_catalog.py
from lowpower_llm_cluster.catalog import llm_candidates, load_catalog, midpoint_price
from lowpower_llm_cluster.scoring import node_score


def test_catalog_has_parts() -> None:
    assert load_catalog()["parts"]


def test_prices_are_ordered() -> None:
    for part in load_catalog()["parts"]:
        assert part["price_min_usd"] <= part["price_max_usd"]
        assert midpoint_price(part) > 0


def test_llm_candidates_get_screening_scores() -> None:
    candidates = llm_candidates(load_catalog()["parts"])
    assert candidates
    assert all(node_score(node) > 0 for node in candidates)


def test_catalog_includes_multiple_hardware_classes() -> None:
    classes = {p.get("hardware_class") for p in load_catalog()["parts"] if p.get("hardware_class")}
    assert {"mini_pc", "edge_ai_developer_kit", "rk3588_sbc", "salvaged_accelerated_apu_board"} <= classes
