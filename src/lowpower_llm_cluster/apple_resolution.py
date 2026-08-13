# src/lowpower_llm_cluster/apple_resolution.py
from __future__ import annotations

import re
from typing import Any


APPLE_PRODUCT_TERMS = (
    "macbook pro",
    "macbook air",
    "mac mini",
    "mac studio",
    "imac",
    "ipad pro",
    "ipad air",
    "iphone",
)

A_NUMBER_HINTS: dict[str, dict[str, Any]] = {
    "A2442": {"product_family": "MacBook Pro", "screen_inches": 14.2, "introduced_year": 2021},
    "A2485": {"product_family": "MacBook Pro", "screen_inches": 16.2, "introduced_year": 2021},
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("–", "-").replace("—", "-").split())


def _first_int(patterns: tuple[str, ...], text: str, *, minimum: int = 0, maximum: int = 100000) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = int(match.group(1))
        if minimum <= value <= maximum:
            return value
    return None


def _capacity_gb(text: str, *, storage: bool = False) -> int | None:
    if storage:
        tb = re.search(r"(?:^|\D)([1-8])\s*tb\s*(?:ssd|storage)?(?:\D|$)", text, re.IGNORECASE)
        if tb:
            return int(tb.group(1)) * 1000
        return _first_int(
            (r"(?:^|\D)(256|512)\s*gb\s*(?:ssd|storage)(?:\D|$)",),
            text,
            minimum=128,
            maximum=8192,
        )
    explicit = _first_int(
        (
            r"(?:^|\D)(8|16|18|24|32|36|48|64|96|128)\s*gb\s*(?:unified\s+memory|memory|ram)(?:\D|$)",
            r"(?:unified\s+memory|memory|ram)\s*[:=-]?\s*(8|16|18|24|32|36|48|64|96|128)\s*gb",
        ),
        text,
        minimum=4,
        maximum=256,
    )
    if explicit is not None:
        return explicit
    # Marketplace titles often use "M1 Max 64GB 2TB" without a RAM label.
    candidates = [int(value) for value in re.findall(r"(?:^|\D)(8|16|18|24|32|36|48|64|96|128)\s*gb(?:\D|$)", text, re.IGNORECASE)]
    return candidates[0] if len(candidates) == 1 else None


def _chip(text: str) -> str | None:
    match = re.search(r"\b(M[1-5])\s*(Ultra|Max|Pro)?\b", text, re.IGNORECASE)
    if not match:
        return None
    suffix = str(match.group(2) or "").title()
    return f"Apple {match.group(1).upper()}{(' ' + suffix) if suffix else ''}"


def _identity(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    a_number = re.search(r"\bA\d{4}\b", text, re.IGNORECASE)
    if a_number:
        value = a_number.group(0).upper()
        facts["apple_a_number"] = value
        facts.update(A_NUMBER_HINTS.get(value, {}))
    model_identifier = re.search(r"\b(?:MacBookPro|MacBookAir|Macmini|MacStudio|iMac)\d{1,2},\d\b", text, re.IGNORECASE)
    if model_identifier:
        facts["model_identifier"] = model_identifier.group(0)
    part_number = re.search(r"\b[A-Z0-9]{4,8}(?:XX)?/[A-Z]\b", text, re.IGNORECASE)
    if part_number:
        facts["apple_part_number"] = part_number.group(0).upper()
    return facts


def _screen(text: str) -> float | None:
    match = re.search(r"\b(13(?:\.3|\.6)?|14(?:\.2)?|15(?:\.3)?|16(?:\.2)?)\s*(?:inch|\"|in\b)", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    if value == 14:
        return 14.2
    if value == 16:
        return 16.2
    return value


def _condition(text: str) -> dict[str, Any]:
    lower = _norm(text)
    cycles = _first_int((r"(?:battery\s*)?(?:cycle|cycles|cycle count)\s*[:=-]?\s*(\d{1,4})",), text, minimum=0, maximum=5000)
    health = _first_int((r"(?:battery\s*)?(?:health|maximum capacity)\s*[:=-]?\s*(\d{1,3})\s*%",), text, minimum=1, maximum=100)
    activation_lock: bool | None = None
    if any(term in lower for term in ("activation lock off", "activation unlocked", "icloud unlocked", "find my off")):
        activation_lock = False
    elif any(term in lower for term in ("activation locked", "icloud locked", "find my locked")):
        activation_lock = True
    mdm: bool | None = None
    if any(term in lower for term in ("no mdm", "mdm free", "not mdm locked")):
        mdm = False
    elif any(term in lower for term in ("mdm locked", "remote management", "device management lock")):
        mdm = True
    return {
        "battery_cycle_count": cycles,
        "battery_health_percent": health,
        "activation_lock": activation_lock,
        "mdm_enrollment": mdm,
    }


def resolve_apple_configuration(title: str, description: str | None = None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Apple marketplace configuration fields without inventing missing SKU details."""
    existing = dict(existing or {})
    combined = " ".join(value for value in (title, description or "") if value)
    lower = _norm(combined)
    if not any(term in lower for term in APPLE_PRODUCT_TERMS):
        return existing

    parsed: dict[str, Any] = {}
    parsed.update(_identity(combined))
    chip = _chip(combined)
    if chip:
        parsed["soc"] = chip
        parsed["cpu"] = chip
    memory = _capacity_gb(combined)
    if memory is not None:
        parsed["memory_capacity_gb"] = memory
    storage = _capacity_gb(combined, storage=True)
    if storage is not None:
        parsed["storage_gb"] = storage
    screen = _screen(combined)
    if screen is not None:
        parsed["screen_inches"] = screen
    cpu_cores = _first_int((r"(\d{1,2})[- ]core\s+cpu",), combined, minimum=4, maximum=32)
    gpu_cores = _first_int((r"(\d{1,3})[- ]core\s+gpu",), combined, minimum=4, maximum=160)
    if cpu_cores is not None:
        parsed["cpu_cores"] = cpu_cores
    if gpu_cores is not None:
        parsed["gpu_cores"] = gpu_cores

    condition = _condition(combined)
    prior_condition = dict(existing.get("condition_evidence") or {})
    for key, value in condition.items():
        if value is not None:
            prior_condition.setdefault(key, value)
    if prior_condition:
        existing["condition_evidence"] = prior_condition

    conflicts: list[str] = []
    for key, value in parsed.items():
        if existing.get(key) is not None and str(existing[key]).casefold() != str(value).casefold():
            conflicts.append(key)
        existing.setdefault(key, value)

    identity_fields = [existing.get("apple_a_number"), existing.get("model_identifier"), existing.get("apple_part_number")]
    required = {
        "identity": any(identity_fields),
        "chip": existing.get("soc") is not None,
        "memory": existing.get("memory_capacity_gb") is not None,
        "storage": existing.get("storage_gb") is not None,
    }
    optional_precision = int(existing.get("gpu_cores") is not None) + int(existing.get("screen_inches") is not None)
    score = 0.0
    score += 0.30 if required["identity"] else 0.0
    score += 0.25 if required["chip"] else 0.0
    score += 0.25 if required["memory"] else 0.0
    score += 0.15 if required["storage"] else 0.0
    score += min(optional_precision * 0.025, 0.05)
    score -= min(len(conflicts) * 0.20, 0.60)
    score = round(max(0.0, min(score, 1.0)), 3)
    existing["apple_resolution"] = {
        "score": score,
        "label": "exact" if score >= 0.95 and not conflicts else "high" if score >= 0.75 else "medium" if score >= 0.50 else "low",
        "exact_configuration": all(required.values()) and not conflicts,
        "required_evidence": required,
        "conflicts": sorted(conflicts),
        "gpu_core_count_explicit": existing.get("gpu_cores") is not None,
        "performance_claim": False,
    }
    return existing
