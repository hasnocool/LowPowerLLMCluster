from lowpower_llm_cluster.catalog import load_catalog
from lowpower_llm_cluster.evidence import memory_basis, performance_evidence
from lowpower_llm_cluster.estimates import model_fit_screen, model_weight_gb
from lowpower_llm_cluster.scoring import catalog_score


def by_id():
    return {p["id"]: p for p in load_catalog()["parts"]}


def test_barebone_does_not_claim_cpu_max_as_included_memory():
    part = by_id()["node-topton-fu05-8745hs"]
    assert part["memory_capacity_gb"] is None
    memory, basis, confidence = memory_basis(part)
    assert memory == part["cpu_max_memory_gb"]
    assert basis == "cpu_theoretical_max_unverified_on_board"
    assert confidence < 0.5


def test_exact_32gb_listing_uses_included_memory():
    part = by_id()["node-tds-8845hs-32g-1t"]
    memory, basis, confidence = memory_basis(part)
    assert memory == 32
    assert basis == "included"
    assert confidence == 1.0


def test_model_fit_is_capacity_only_and_conservative():
    part = by_id()["special-amd-bc250-16g"]
    result = model_fit_screen(part, params_b=14, bits_per_weight=4)
    assert result["weights_only_gb"] == 7.0
    assert result["status"] == "reasonable_capacity_candidate"
    assert "does not predict tokens/sec" in result["warning"]


def test_no_performance_evidence_defaults_to_unknown():
    evidence = performance_evidence(by_id()["special-amd-bc250-16g"] )
    assert evidence["source_type"] == "unknown"
    assert evidence["confidence"] == "unknown"


def test_catalog_score_is_not_zero_for_buyable_llm_candidate():
    assert catalog_score(by_id()["node-tds-8845hs-32g-1t"]) > 0


def test_weight_formula():
    assert model_weight_gb(8, 4) == 4.0
