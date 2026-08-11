from __future__ import annotations

from typing import Any

from .catalog import midpoint_price
from .evidence import memory_basis

_MATURITY = {
    "mature_jetpack_cuda": 1.00,
    "mainstream_linux": 0.95,
    "vendor_genai_stack": 0.95,
    "vendor_llm_toolchain": 0.90,
    "active_vendor_llm_stack": 0.90,
    "community_linux_rk3588": 0.72,
    "mature_fpga_toolchain": 0.72,
    "active_vendor_edge_stack": 0.70,
    "experimental_vulkan": 0.52,
    "discontinued_limited_support": 0.35,
    "eol_legacy_stack": 0.25,
}
_RISK = {"low": 1.0, "medium": 0.82, "high": 0.58}
_STATUS = {
    "current_reference": 1.0, "available": 1.0, "observed_market": 0.95,
    "market_reference": 0.85, "watch": 0.65, "sold_out_reference": 0.45,
}


def catalog_score(part: dict[str, Any]) -> float:
    """Buying/research shortlist score; deliberately not an inference benchmark.

    Rewards affordability, memory *potential*, low published power hints, software
    maturity, lifecycle/availability and lower ownership risk. It never uses TOPS,
    TFLOPS or invented tokens/sec. Configurable/unverified memory is discounted.
    """
    if not part.get("llm_candidate", part.get("category") == "compute_node"):
        return 0.0
    mid = midpoint_price(part)
    if mid is None:
        return 0.0

    memory_gb, _, memory_conf = memory_basis(part)
    memory = max(memory_gb or 8.0, 1.0)
    power_hint = part.get("power_target_w") or part.get("ctdp_min_w") or part.get("default_tdp_w")
    power = max(float(power_hint or 30.0), 1.0)

    value_term = min(2.5, 250.0 / max(float(mid), 1.0))
    memory_term = min(memory, 128.0) / 32.0 * memory_conf
    power_term = min(2.0, 25.0 / power)
    maturity_term = _MATURITY.get(str(part.get("software_maturity", "")), 0.70)
    risk_term = _RISK.get(str(part.get("risk_level", "medium")), 0.82)
    status_term = _STATUS.get(str(part.get("listing_status", "")), 0.80)

    score = 20.0 * (
        0.30 * min(value_term, 2.0) / 2.0
        + 0.28 * min(memory_term, 2.0) / 2.0
        + 0.16 * min(power_term, 2.0) / 2.0
        + 0.14 * maturity_term
        + 0.07 * risk_term
        + 0.05 * status_term
    )
    return round(score, 2)


def node_score(part: dict[str, Any]) -> float:
    """Backward-compatible alias for the catalog-first shortlist score."""
    return catalog_score(part)
