# src/lowpower_llm_cluster/scoring.py
from __future__ import annotations

from typing import Any

from .catalog import midpoint_price

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


def node_score(part: dict[str, Any]) -> float:
    """Return a transparent *screening* score, never a benchmark claim.

    Cross-platform shortlist scores reward affordable usable memory, low target
    power, software maturity and useful I/O. Accelerator TOPS/TFLOPS are *not*
    multiplied into the score because they are not comparable across runtimes,
    precisions or workloads. Measured inference data belongs in benchmark records.
    """
    if not part.get("llm_candidate", part.get("category") == "compute_node"):
        return 0.0

    mid_price = midpoint_price(part)
    if mid_price is None:
        return 0.0

    price = max(mid_price, 1.0)
    memory = max(float(part.get("memory_capacity_gb") or part.get("cpu_max_memory_gb") or 1), 1.0)
    power = max(float(part.get("power_target_w") or part.get("ctdp_min_w") or part.get("default_tdp_w") or 25), 1.0)
    bandwidth = float(part.get("memory_bandwidth_gbps") or 0.0)

    memory_term = min(memory, 128.0) / 32.0
    power_term = 25.0 / power
    value_term = 250.0 / price
    bandwidth_term = 1.0 + min(bandwidth, 500.0) / 1000.0
    maturity_term = _MATURITY.get(str(part.get("software_maturity", "")), 0.70)
    risk_term = _RISK.get(str(part.get("risk_level", "medium")), 0.82)

    io_bonus = 1.0
    network = str(part.get("network", "")).lower()
    expansion = str(part.get("expandability", "")).lower()
    host_mode = str(part.get("host_mode", "")).lower()
    if "2.5" in network:
        io_bonus += 0.08
    if "oculink" in expansion or "pcie x16" in expansion:
        io_bonus += 0.08
    if "nvme" in str(part.get("storage", "")).lower():
        io_bonus += 0.04
    if host_mode in {"m2_pcie_gen3_x2", "pcie_x16", "pcie_x8"}:
        io_bonus += 0.03

    return round(memory_term * power_term * value_term * bandwidth_term * maturity_term * risk_term * io_bonus, 2)
