# src/lowpower_llm_cluster/factory_firmware.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .bios_versioning import shipped_bios_meets_requirement
from .catalog import project_root


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").replace("-", " ").split())


def _revision(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip().upper().removeprefix("REV.").removeprefix("REV ").strip().rstrip(". ,;:)") or None


def load_factory_firmware_rules(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "firmware" / "factory-firmware-rules.json"
    if not target.exists():
        return {"schema_version": 1, "rules": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _identity_matches(rule: dict[str, Any], listing: dict[str, Any]) -> bool:
    cfg = dict(listing.get("configuration") or {})
    manufacturer = _norm(cfg.get("manufacturer") or listing.get("manufacturer"))
    model = _norm(cfg.get("mpn") or cfg.get("model") or listing.get("sku") or listing.get("title"))
    rule_manufacturer = _norm(rule.get("manufacturer"))
    rule_model = _norm(rule.get("model") or rule.get("mpn"))
    if rule_manufacturer and manufacturer and rule_manufacturer != manufacturer:
        return False
    if rule_model and model and rule_model not in model:
        return False
    return bool(rule_manufacturer or rule_model)


def resolve_factory_firmware(
    listing: dict[str, Any],
    *,
    required_bios: str | None = None,
    source_url: str | None = None,
    provider: str | None = None,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve factory/shipped BIOS only from explicit vendor-published mappings.

    No generic serial decoding is attempted. Serial patterns, manufacture batches, PCB
    revisions, and physical label/sticker methods are admitted only when backed by an
    explicit manufacturer source. A documented label method may take the observed label
    value as the factory BIOS; it does not require a pre-enumerated BIOS string.
    """
    cfg = dict(listing.get("configuration") or {})
    seller_fw = dict(cfg.get("seller_firmware_evidence") or {})
    serial = str(cfg.get("serial_number") or seller_fw.get("serial_number") or "").strip()
    batch = str(cfg.get("manufacture_batch") or cfg.get("batch_code") or seller_fw.get("manufacture_batch") or "").strip()
    revision = _revision(cfg.get("board_revision") or seller_fw.get("board_revision"))
    factory_label = str(cfg.get("factory_bios_label") or seller_fw.get("factory_bios_label") or "").strip()

    matches: list[tuple[int, dict[str, Any], str, str]] = []
    payload = rules or load_factory_firmware_rules()
    for rule in payload.get("rules") or []:
        if not rule.get("enabled", True) or not str(rule.get("source_url") or "").startswith("https://"):
            continue
        if not _identity_matches(rule, listing):
            continue
        kind = str(rule.get("match_kind") or "").casefold()
        configured_version = str(rule.get("factory_bios_version") or "").strip()
        score = 0
        reason = ""
        resolved_version = configured_version
        if kind == "exact_serial" and configured_version and serial and serial in {str(v) for v in rule.get("serials") or []}:
            score, reason = 100, "exact serial matched a vendor-published factory firmware mapping"
        elif kind == "serial_regex" and configured_version and serial and rule.get("serial_pattern"):
            if re.fullmatch(str(rule["serial_pattern"]), serial):
                score, reason = 95, "serial matched a vendor-published decoding rule"
        elif kind == "manufacture_batch" and configured_version and batch and batch in {str(v) for v in rule.get("batches") or []}:
            score, reason = 90, "manufacture batch matched a vendor-published factory firmware mapping"
        elif kind == "board_revision" and configured_version and revision and revision in {_revision(v) for v in rule.get("board_revisions") or []}:
            score, reason = 80, "PCB revision matched an explicit vendor factory-firmware mapping"
        elif kind == "factory_bios_label" and factory_label and rule.get("observed_label_is_factory_bios") is True:
            score, reason, resolved_version = 98, "physical factory-BIOS label/sticker interpreted by the documented vendor method", factory_label
        elif kind == "factory_bios_label" and factory_label and configured_version and _norm(factory_label) == _norm(configured_version):
            score, reason = 98, "physical factory-BIOS label/sticker matched the documented vendor value"
        if score and resolved_version:
            matches.append((score, rule, reason, resolved_version))

    if not matches:
        return {
            "status": "unresolved",
            "factory_bios_version": None,
            "board_revision": revision,
            "serial_number_present": bool(serial),
            "manufacture_batch_present": bool(batch),
            "factory_bios_label_present": bool(factory_label),
            "reason": "no explicit vendor-published serial/batch/revision/factory-label mapping matched",
            "manufacturer_authority": False,
        }

    score, rule, reason, version = max(matches, key=lambda row: row[0])
    comparison = shipped_bios_meets_requirement(
        version,
        required_bios,
        source_url=source_url or rule.get("source_url"),
        provider=provider,
    ) if required_bios else None
    return {
        "status": "verified_factory_firmware",
        "factory_bios_version": version,
        "board_revision": revision or _revision((rule.get("board_revisions") or [None])[0]),
        "match_kind": rule.get("match_kind"),
        "rule_id": rule.get("id"),
        "source_url": rule.get("source_url"),
        "source_type": "manufacturer_factory_firmware_mapping",
        "confidence": "exact" if score >= 95 else "high",
        "score": score,
        "reason": reason,
        "version_comparison": comparison,
        "meets_minimum": comparison.get("meets_minimum") if comparison else None,
        "manufacturer_authority": True,
    }
