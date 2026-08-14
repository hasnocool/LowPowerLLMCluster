from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _url(value: str) -> str:
    parsed = urlsplit(value.strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


def _id(record: Mapping[str, Any]) -> str:
    manufacturer = str(record.get("manufacturer", "")).strip().lower()
    part = str(record.get("mpn") or record.get("sku") or "").strip().lower()
    identity = f"{manufacturer}|{part}" if manufacturer and part else _url(str(record.get("listing_url", "")))
    return "auto-" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def evaluate(record: Mapping[str, Any], *, min_source_confidence: float = 0.80, min_sku_confidence: float = 0.55) -> list[str]:
    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    reasons: list[str] = []
    if not str(record.get("listing_url", "")).startswith("https://"): reasons.append("missing_https_product_url")
    if not str(record.get("title", "")).strip(): reasons.append("missing_title")
    if not str(record.get("manufacturer", "")).strip(): reasons.append("missing_manufacturer")
    if str(attrs.get("discovery_kind", "")).lower() == "announcement": reasons.append("announcement_not_product")
    if attrs.get("metadata_fallback") is True: reasons.append("metadata_fallback_unverified")
    if float(record.get("source_confidence") or 0) < min_source_confidence: reasons.append("source_confidence_below_threshold")
    if float(record.get("sku_confidence") or 0) < min_sku_confidence and not (record.get("sku") or record.get("mpn")): reasons.append("identity_confidence_below_threshold")
    if record.get("in_stock") is False: reasons.append("out_of_stock")
    return reasons


def _category(record: Mapping[str, Any]) -> str:
    form = str(record.get("form_factor", "")).lower()
    title = str(record.get("title", "")).lower()
    if form in {"mini_pc", "mini_pc_barebone"} or "mini pc" in title: return "mini_pc"
    if form == "sbc" or "single board" in title: return "sbc"
    if form == "pcie_card" or any(x in title for x in (" gpu", "rtx ", "radeon ")): return "gpu_accelerator"
    if any(x in title for x in ("hailo", "coral", "npu", "accelerator")): return "ai_asic_accelerator"
    return "compute_node"


def canonical_part(record: Mapping[str, Any]) -> dict[str, Any]:
    attrs = record.get("raw_attributes") if isinstance(record.get("raw_attributes"), Mapping) else {}
    price = record.get("price")
    currency = str(record.get("currency") or "USD").upper()
    usd = float(price) if currency == "USD" and isinstance(price, (int, float)) else None
    observed = str(record.get("observed_at") or datetime.now(UTC).isoformat())
    category = _category(record)
    result: dict[str, Any] = {
        "id": _id(record), "category": category, "name": str(record.get("title", "")).strip(),
        "vendor": str(record.get("manufacturer", "")).strip(), "price_min_usd": usd, "price_max_usd": usd,
        "price_status": "observed_market" if usd is not None else "price_not_resolved", "moq": 1,
        "url": str(record.get("listing_url", "")), "source_url": str(record.get("listing_url", "")),
        "verified_on": observed[:10], "listing_status": "autonomously_verified_active",
        "plain_language": "Automatically promoted after passing product identity and source-evidence gates.",
        "source_notes": f"Discovery source={record.get('source')}; source confidence={record.get('source_confidence')}; SKU confidence={record.get('sku_confidence')}.",
        "llm_candidate": bool(attrs.get("llm_candidate", True)), "hardware_class": str(attrs.get("hardware_class") or category),
        "software_maturity": str(attrs.get("software_maturity") or "unverified_runtime_support"),
        "risk_level": str(attrs.get("risk_level") or "medium"), "lifecycle_status": str(attrs.get("lifecycle_status") or "current"),
        "promotion_provenance": {"source": record.get("source"), "source_id": record.get("source_id"), "observed_at": observed, "sku": record.get("sku"), "mpn": record.get("mpn")},
    }
    for key in ("cpu", "architecture", "memory_type", "memory_capacity_gb", "max_memory_gb", "storage", "network", "expandability", "power_target_w", "accelerator", "software_stack", "llm_support"):
        if attrs.get(key) not in (None, "", [], {}): result[key] = attrs[key]
    return result


def promote(records: Sequence[Mapping[str, Any]], *, catalog_path: str | Path = "data/catalog/auto-promoted.json", report_path: str | Path = "results/promotion-latest.json", min_source_confidence: float = 0.80, min_sku_confidence: float = 0.55) -> dict[str, Any]:
    catalog_path, report_path = Path(catalog_path), Path(report_path)
    existing: dict[str, dict[str, Any]] = {}
    if catalog_path.exists():
        try:
            for item in json.loads(catalog_path.read_text(encoding="utf-8")).get("parts", []):
                if isinstance(item, dict) and item.get("id"): existing[str(item["id"])] = dict(item)
        except (OSError, json.JSONDecodeError): pass
    promoted: list[str] = []; updated: list[str] = []; held: list[dict[str, Any]] = []
    for record in records:
        reasons = evaluate(record, min_source_confidence=min_source_confidence, min_sku_confidence=min_sku_confidence)
        if reasons:
            held.append({"source": record.get("source"), "source_id": record.get("source_id"), "title": record.get("title"), "reasons": reasons}); continue
        part = canonical_part(record); pid = str(part["id"])
        (updated if pid in existing else promoted).append(pid); existing[pid] = part
    parts = sorted(existing.values(), key=lambda x: (str(x.get("category", "")), str(x.get("vendor", "")), str(x.get("name", ""))))
    _atomic_json(catalog_path, {"parts": parts})
    report = {"generated_at": datetime.now(UTC).isoformat(), "canonical_total": len(parts), "promoted_count": len(promoted), "updated_count": len(updated), "held_count": len(held), "promoted": promoted, "updated": updated, "held": held}
    _atomic_json(report_path, report)
    return report


def records_from_output(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists(): return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [dict(x) for x in payload.get("observations", []) if isinstance(x, dict)] if isinstance(payload, dict) else []
