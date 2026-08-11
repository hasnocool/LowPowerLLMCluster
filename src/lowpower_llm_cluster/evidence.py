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


def memory_basis(part: dict[str, Any]) -> tuple[float | None, str, float]:
    """Return (GB, basis label, confidence weight) for catalog capacity screening.

    Included/fixed memory is strong evidence. A verified board maximum is useful
    for planning but still costs extra. A CPU theoretical maximum is deliberately
    treated as weak evidence because the actual board BIOS/slots may support less.
    """
    installed = part.get("memory_capacity_gb")
    if installed is not None:
        return float(installed), str(part.get("memory_config_status", "included_or_fixed")), 1.0
    board_max = part.get("max_memory_gb")
    if board_max is not None:
        return float(board_max), "configurable_max", 0.82
    cpu_max = part.get("cpu_max_memory_gb")
    if cpu_max is not None:
        return float(cpu_max), "cpu_theoretical_max_unverified_on_board", 0.20
    return None, "unknown", 0.25


def verified_memory_gb(part: dict[str, Any]) -> float | None:
    """Return only included/fixed or verified board-max memory, never CPU theoretical max."""
    installed = part.get("memory_capacity_gb")
    if installed is not None:
        return float(installed)
    board_max = part.get("max_memory_gb")
    if board_max is not None:
        return float(board_max)
    return None
