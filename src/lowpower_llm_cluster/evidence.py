# src/lowpower_llm_cluster/evidence.py
from __future__ import annotations

from typing import Any

PERFORMANCE_SOURCES = {
    "measured_local",
    "community_measured",
    "vendor_measured",
    "derived_estimate",
    "spec_based_estimate",
    "unknown",
}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}


def performance_evidence(part: dict[str, Any]) -> dict[str, str]:
    """Return explicit performance provenance without inventing evidence."""
    raw = part.get("performance_evidence") or {}
    source_type = str(raw.get("source_type", "unknown"))
    confidence = str(raw.get("confidence", "unknown"))
    if source_type not in PERFORMANCE_SOURCES:
        source_type = "unknown"
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "unknown"
    return {
        "source_type": source_type,
        "confidence": confidence,
        "source_url": str(raw.get("source_url", "")),
        "notes": str(raw.get("notes", "")),
    }


def board_memory_evidence(part: dict[str, Any]) -> dict[str, Any]:
    """Describe whether max RAM is a board claim or only a processor-theoretical limit."""
    board_max = part.get("max_memory_gb")
    source_url = str(part.get("max_memory_source_url", ""))
    if board_max is not None:
        return {
            "max_memory_gb": float(board_max),
            "basis": "board_verified" if source_url.startswith("https://") else "board_claim_legacy_unlinked",
            "source_url": source_url,
            "verified_on": str(part.get("max_memory_verified_on", "")),
            "confidence_weight": 0.92 if source_url.startswith("https://") else 0.82,
        }
    cpu_max = part.get("cpu_max_memory_gb")
    if cpu_max is not None:
        return {
            "max_memory_gb": float(cpu_max),
            "basis": "cpu_theoretical_max_unverified_on_board",
            "source_url": str(part.get("cpu_memory_source_url", "")),
            "verified_on": "",
            "confidence_weight": 0.20,
        }
    return {"max_memory_gb": None, "basis": "unknown", "source_url": "", "verified_on": "", "confidence_weight": 0.25}


def memory_basis(part: dict[str, Any]) -> tuple[float | None, str, float]:
    """Return (GB, basis label, confidence weight) for catalog capacity screening.

    Included/fixed memory is strong evidence. A verified board maximum is useful
    for planning but still costs extra. A CPU theoretical maximum is deliberately
    treated as weak evidence because the actual board BIOS/slots may support less.
    """
    installed = part.get("memory_capacity_gb")
    if installed is not None:
        return float(installed), str(part.get("memory_config_status", "included_or_fixed")), 1.0
    evidence = board_memory_evidence(part)
    return evidence["max_memory_gb"], evidence["basis"].replace("board_verified", "configurable_max").replace("board_claim_legacy_unlinked", "configurable_max"), float(evidence["confidence_weight"])


def verified_memory_gb(part: dict[str, Any]) -> float | None:
    """Return only included/fixed or board-max memory, never CPU theoretical max."""
    installed = part.get("memory_capacity_gb")
    if installed is not None:
        return float(installed)
    board_max = part.get("max_memory_gb")
    if board_max is not None:
        return float(board_max)
    return None
