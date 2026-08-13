# src/lowpower_llm_cluster/normalization.py
from __future__ import annotations

import re
from typing import Any, Mapping

from .discovery import ProductObservation

_FORM_FACTOR_ALIASES = {
    "mini pc": "mini_pc",
    "minipc": "mini_pc",
    "barebone": "mini_pc_barebone",
    "sbc": "sbc",
    "single board": "sbc",
    "m.2": "m2_module",
    "pcie": "pcie_card",
    "mini-itx": "mini_itx",
    "micro-atx": "micro_atx",
    "matx": "micro_atx",
}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_dimensions(attributes: Mapping[str, Any]) -> dict[str, float] | None:
    direct = {
        "width_mm": _number(attributes.get("width_mm")),
        "depth_mm": _number(attributes.get("depth_mm")),
        "height_mm": _number(attributes.get("height_mm")),
    }
    if all(value is not None for value in direct.values()):
        return {key: float(value) for key, value in direct.items() if value is not None}

    raw = str(attributes.get("dimensions", ""))
    values = re.findall(r"(\d+(?:\.\d+)?)", raw)
    if len(values) >= 3 and "mm" in raw.lower():
        return {"width_mm": float(values[0]), "depth_mm": float(values[1]), "height_mm": float(values[2])}
    return None


def _form_factor(title: str, attributes: Mapping[str, Any]) -> str:
    explicit = str(attributes.get("form_factor", "")).strip().lower()
    haystack = f"{explicit} {title.lower()}"
    for token, normalized in _FORM_FACTOR_ALIASES.items():
        if token in haystack:
            return normalized
    return explicit.replace(" ", "_") or "unknown"


def seller_confidence(observation: ProductObservation, *, source_trust: float = 0.65) -> float:
    score = max(0.0, min(1.0, source_trust)) * 0.45
    if observation.seller_verified is True:
        score += 0.22
    elif observation.seller_verified is False:
        score -= 0.08
    if observation.seller_rating is not None:
        rating = observation.seller_rating
        if rating > 5:
            rating /= 20.0
        score += max(0.0, min(1.0, rating / 5.0)) * 0.20
    if observation.seller_review_count is not None:
        score += min(1.0, max(0, observation.seller_review_count) / 250.0) * 0.13
    return round(max(0.0, min(1.0, score)), 3)


def sku_confidence(observation: ProductObservation) -> float:
    """Confidence that an observation represents one exact purchasable configuration."""
    score = 0.18
    if observation.manufacturer.strip():
        score += 0.15
    if observation.mpn.strip():
        score += 0.28
    if observation.sku.strip():
        score += 0.20
    attrs = observation.attributes
    config_keys = {"cpu", "memory_capacity_gb", "storage", "ram", "ssd", "model"}
    present = sum(1 for key in config_keys if attrs.get(key) not in (None, ""))
    score += min(0.19, present * 0.038)
    ambiguous = any(token in observation.title.lower() for token in ("/", "8gb 16gb", "16gb 32gb", "barebone/", "optional"))
    if ambiguous:
        score -= 0.16
    return round(max(0.0, min(1.0, score)), 3)


def normalize_observation(observation: ProductObservation, *, source_trust: float = 0.65) -> dict[str, Any]:
    attrs = dict(observation.attributes)
    voltage = _number(attrs.get("dc_input_v") or attrs.get("input_voltage_v"))
    voltage_min = _number(attrs.get("dc_input_min_v"))
    voltage_max = _number(attrs.get("dc_input_max_v"))
    board_ram_max = _number(attrs.get("board_max_memory_gb") or attrs.get("max_memory_gb"))
    cpu_ram_max = _number(attrs.get("cpu_max_memory_gb"))
    ram_source = str(attrs.get("board_max_memory_source_url", ""))

    return {
        "source": observation.source,
        "source_id": observation.source_id,
        "listing_url": observation.listing_url,
        "title": observation.title,
        "manufacturer": observation.manufacturer or str(attrs.get("manufacturer", "")),
        "sku": observation.sku,
        "mpn": observation.mpn,
        "price": observation.price,
        "currency": observation.currency.upper(),
        "shipping": observation.shipping,
        "seller": observation.seller,
        "seller_confidence": seller_confidence(observation, source_trust=source_trust),
        "source_confidence": round(max(0.0, min(1.0, source_trust)), 3),
        "sku_confidence": sku_confidence(observation),
        "form_factor": _form_factor(observation.title, attrs),
        "dimensions_mm": _normalized_dimensions(attrs),
        "dc_input": {
            "voltage_v": voltage,
            "min_v": voltage_min,
            "max_v": voltage_max,
            "connector": attrs.get("dc_connector"),
        },
        "psu_requirements": attrs.get("psu_requirements") or attrs.get("power_adapter"),
        "cooling_requirements": attrs.get("cooling_requirements") or attrs.get("cooling"),
        "host_requirements": attrs.get("host_requirements"),
        "board_max_memory_gb": board_ram_max,
        "board_max_memory_source_url": ram_source or None,
        "cpu_theoretical_max_memory_gb": cpu_ram_max,
        "board_memory_verified": bool(board_ram_max is not None and ram_source.startswith("https://")),
        "in_stock": observation.in_stock,
        "observed_at": observation.observed_at,
        "raw_attributes": attrs,
    }
