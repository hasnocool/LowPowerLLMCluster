# src/lowpower_llm_cluster/seller_firmware.py
from __future__ import annotations

from typing import Any

from .bios_versioning import manufacturer_from_source, shipped_bios_meets_requirement
from .factory_firmware import resolve_factory_firmware
from .firmware_history import bios_history_for_revision


def correlate_seller_firmware(
    cpu_bios: dict[str, Any],
    seller_evidence: dict[str, Any] | None,
    revision_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Correlate seller firmware claims with official revision/factory evidence.

    Seller text can identify a physical board, but it never becomes manufacturer authority.
    A separate factory-firmware resolver may promote serial/batch/revision/sticker evidence
    only when a manufacturer-published rule explicitly defines that relationship.
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

    manufacturer = manufacturer_from_source(source_url, provider)
    factory_listing = {
        "title": seller.get("title") or "",
        "sku": seller.get("mpn"),
        "configuration": {
            "manufacturer": manufacturer,
            "mpn": seller.get("mpn"),
            "board_revision": revision,
            "serial_number": seller.get("serial_number"),
            "manufacture_batch": seller.get("manufacture_batch"),
            "factory_bios_label": seller.get("factory_bios_label"),
            "seller_firmware_evidence": seller,
        },
    }
    factory = resolve_factory_firmware(
        factory_listing,
        required_bios=str(required) if required else None,
        source_url=source_url,
        provider=provider,
    )

    confidence = "unknown"
    status = "unresolved"
    reasons: list[str] = []
    if installed:
        confidence = "medium"
        reasons.append("seller states currently installed BIOS/UEFI")
    if revision:
        reasons.append("seller states board/PCB revision")
    if seller.get("serial_number"):
        reasons.append("seller exposes a board serial number; no decoding is assumed without a vendor-published rule")
    if seller.get("manufacture_batch"):
        reasons.append("seller exposes a manufacture/batch code; no mapping is assumed without a vendor-published rule")
    if installed_in_revision_history:
        confidence = "high"
        reasons.append("seller-stated installed BIOS exists in official history for the seller-stated board revision")
    elif installed and revision and scoped.get("status") == "revision_scoped":
        reasons.append("official revision-scoped history was found, but the seller-stated BIOS version was not present")
    if factory.get("status") == "verified_factory_firmware":
        confidence = "exact" if factory.get("confidence") == "exact" else "high"
        reasons.append(str(factory.get("reason") or "manufacturer-published factory firmware evidence matched"))

    if factory.get("meets_minimum") is True:
        status = "manufacturer_factory_firmware_meets_cpu_minimum"
    elif factory.get("meets_minimum") is False:
        status = "manufacturer_factory_firmware_below_cpu_minimum"
    elif meets_minimum is True:
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
        "factory_firmware": factory,
        "source_type": seller.get("source_type") or "seller_listing_text",
        "confidence": confidence,
        "reasons": reasons,
        "manufacturer_authority": factory.get("manufacturer_authority") is True,
    }
