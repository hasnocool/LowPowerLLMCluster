# src/lowpower_llm_cluster/seller_firmware.py
from __future__ import annotations

from typing import Any

from .bios_versioning import shipped_bios_meets_requirement
from .firmware_history import bios_history_for_revision


def correlate_seller_firmware(
    cpu_bios: dict[str, Any],
    seller_evidence: dict[str, Any] | None,
    revision_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Correlate lower-confidence seller firmware claims with official revision history.

    Seller text can describe the physical board in a listing, but it never overrides
    manufacturer CPU support or official firmware history. The result is therefore a
    readiness signal with explicit evidence boundaries, not a manufacturer fact.
    """
    seller = dict(seller_evidence or {})
    revision = seller.get("board_revision")
    installed = seller.get("installed_bios_version")
    required = cpu_bios.get("minimum_bios_version")
    source_url = cpu_bios.get("source_url")
    provider = cpu_bios.get("provider")

    scoped = bios_history_for_revision(list(revision_history or []), str(revision) if revision else None)
    history_versions = {
        str(row.get("version") or "").casefold()
        for row in scoped.get("rows") or []
        if row.get("version")
    }
    installed_in_revision_history = bool(installed and str(installed).casefold() in history_versions)

    comparison = None
    meets_minimum = None
    if installed and required:
        comparison = shipped_bios_meets_requirement(str(installed), str(required), source_url=source_url, provider=provider)
        meets_minimum = comparison.get("meets_minimum")

    confidence = "unknown"
    status = "unresolved"
    reasons: list[str] = []
    if installed:
        confidence = "medium"
        reasons.append("seller states currently installed BIOS/UEFI")
    if revision:
        reasons.append("seller states board/PCB revision")
    if installed_in_revision_history:
        confidence = "high"
        reasons.append("seller-stated installed BIOS exists in official history for the seller-stated board revision")
    elif installed and revision and scoped.get("status") == "revision_scoped":
        reasons.append("official revision-scoped history was found, but the seller-stated BIOS version was not present")

    if meets_minimum is True:
        status = "seller_claim_meets_cpu_minimum"
    elif meets_minimum is False:
        status = "seller_claim_below_cpu_minimum"
    elif installed:
        status = "seller_claim_version_order_unresolved"

    return {
        "status": status,
        "board_revision": revision,
        "installed_bios_version": installed,
        "minimum_bios_version": required,
        "meets_minimum": meets_minimum,
        "version_comparison": comparison,
        "revision_history_status": scoped.get("status"),
        "installed_bios_in_revision_history": installed_in_revision_history,
        "official_revision_history_rows": len(scoped.get("rows") or []),
        "source_type": seller.get("source_type") or "seller_listing_text",
        "confidence": confidence,
        "reasons": reasons,
        "manufacturer_authority": False,
    }
