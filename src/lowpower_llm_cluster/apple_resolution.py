# src/lowpower_llm_cluster/apple_resolution.py
from __future__ import annotations

import json
import re
from pathlib import Path
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

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "evidence" / "apple-identifiers.json"
_IDENTIFIER_REGISTRY = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("–", "-").replace("—", "-").split())


def _same(left: Any, right: Any) -> bool:
    return str(left).casefold() == str(right).casefold()


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
    model_identifier = re.search(
        r"\b(?:MacBookPro|MacBookAir|Macmini|MacStudio|iMac|Mac)\d{1,2},\d{1,2}\b",
        text,
        re.IGNORECASE,
    )
    if model_identifier:
        facts["model_identifier"] = model_identifier.group(0)
    part_number = re.search(r"\b[A-Z0-9]{5,12}/[A-Z]\b", text, re.IGNORECASE)
    if part_number:
        facts["apple_part_number"] = part_number.group(0).upper()
    return facts


def _part_pattern_matches(pattern: str, part_number: str) -> bool:
    normalized = pattern.upper()
    expression = re.escape(normalized).replace("XX", r"[A-Z0-9]{1,3}")
    return re.fullmatch(expression, part_number.upper()) is not None


def _registry_matches(identity: dict[str, Any]) -> list[dict[str, Any]]:
    a_number = str(identity.get("apple_a_number") or "").upper()
    model_identifier = str(identity.get("model_identifier") or "").casefold()
    part_number = str(identity.get("apple_part_number") or "").upper()
    matches: list[dict[str, Any]] = []

    for record in _IDENTIFIER_REGISTRY.get("records", []):
        match_types: list[str] = []
        matched_values: list[str] = []
        if a_number and a_number in {str(value).upper() for value in record.get("a_numbers", [])}:
            match_types.append("a_number")
            matched_values.append(a_number)
        if model_identifier and model_identifier in {str(value).casefold() for value in record.get("model_identifiers", [])}:
            match_types.append("model_identifier")
            matched_values.append(str(identity["model_identifier"]))
        if part_number:
            matched_pattern = next(
                (pattern for pattern in record.get("part_number_patterns", []) if _part_pattern_matches(str(pattern), part_number)),
                None,
            )
            if matched_pattern:
                match_types.append("part_number")
                matched_values.append(part_number)
        if match_types:
            matches.append({"record": record, "match_types": match_types, "matched_values": matched_values})
    return matches


def _registry_facts(identity: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    matches = _registry_matches(identity)
    if not matches:
        return {}, [], []
    if len(matches) > 1:
        evidence = [
            {
                "record_id": str(match["record"].get("id")),
                "authority": "apple_support",
                "source_url": str(match["record"].get("source_url")),
                "match_types": list(match["match_types"]),
                "matched_values": list(match["matched_values"]),
            }
            for match in matches
        ]
        return {}, ["registry_identity_ambiguous"], evidence

    match = matches[0]
    record = match["record"]
    facts: dict[str, Any] = {
        "product_family": record.get("product_family"),
        "introduced_year": record.get("introduced_year"),
    }
    if record.get("screen_inches") is not None:
        facts["screen_inches"] = record["screen_inches"]
    if record.get("soc"):
        facts["soc"] = record["soc"]
        facts["cpu"] = record["soc"]
    if record.get("soc_candidates"):
        facts["soc_candidates"] = list(record["soc_candidates"])

    model_identifiers = list(record.get("model_identifiers", []))
    if not identity.get("model_identifier"):
        if len(model_identifiers) == 1:
            facts["model_identifier"] = model_identifiers[0]
        elif model_identifiers:
            facts["model_identifier_candidates"] = model_identifiers

    a_numbers = list(record.get("a_numbers", []))
    if not identity.get("apple_a_number"):
        if len(a_numbers) == 1:
            facts["apple_a_number"] = a_numbers[0]
        elif a_numbers:
            facts["apple_a_number_candidates"] = a_numbers

    evidence = [{
        "record_id": str(record.get("id")),
        "authority": "apple_support",
        "source_url": str(record.get("source_url")),
        "a_number_source_url": record.get("a_number_source_url"),
        "match_types": list(match["match_types"]),
        "matched_values": list(match["matched_values"]),
    }]
    return {key: value for key, value in facts.items() if value is not None}, [], evidence


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


def _merge_registry_facts(parsed: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    for key, value in registry.items():
        if key == "soc_candidates":
            explicit_soc = parsed.get("soc")
            if explicit_soc is not None and not any(_same(explicit_soc, candidate) for candidate in value):
                conflicts.append("soc")
            parsed.setdefault(key, value)
            continue
        if key == "model_identifier_candidates":
            explicit_model = parsed.get("model_identifier")
            if explicit_model is not None and not any(_same(explicit_model, candidate) for candidate in value):
                conflicts.append("model_identifier")
            parsed.setdefault(key, value)
            continue
        if key == "apple_a_number_candidates":
            explicit_a = parsed.get("apple_a_number")
            if explicit_a is not None and not any(_same(explicit_a, candidate) for candidate in value):
                conflicts.append("apple_a_number")
            parsed.setdefault(key, value)
            continue
        if parsed.get(key) is not None and not _same(parsed[key], value):
            conflicts.append(key)
            continue
        parsed.setdefault(key, value)
    return conflicts


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

    registry_facts, registry_conflicts, identifier_evidence = _registry_facts(parsed)
    parser_conflicts = _merge_registry_facts(parsed, registry_facts)

    condition = _condition(combined)
    prior_condition = dict(existing.get("condition_evidence") or {})
    for key, value in condition.items():
        if value is not None:
            prior_condition.setdefault(key, value)
    if prior_condition:
        existing["condition_evidence"] = prior_condition
    if identifier_evidence:
        existing["apple_identifier_evidence"] = identifier_evidence

    conflicts: list[str] = [*registry_conflicts, *parser_conflicts]
    for key, value in parsed.items():
        if existing.get(key) is not None and not _same(existing[key], value):
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
    unique_conflicts = sorted(set(conflicts))
    score = 0.0
    score += 0.30 if required["identity"] else 0.0
    score += 0.25 if required["chip"] else 0.0
    score += 0.25 if required["memory"] else 0.0
    score += 0.15 if required["storage"] else 0.0
    score += min(optional_precision * 0.025, 0.05)
    score -= min(len(unique_conflicts) * 0.20, 0.60)
    score = round(max(0.0, min(score, 1.0)), 3)
    existing["apple_resolution"] = {
        "score": score,
        "label": "exact" if score >= 0.95 and not unique_conflicts else "high" if score >= 0.75 else "medium" if score >= 0.50 else "low",
        "exact_configuration": all(required.values()) and not unique_conflicts,
        "required_evidence": required,
        "conflicts": unique_conflicts,
        "gpu_core_count_explicit": existing.get("gpu_cores") is not None,
        "identifier_authority": "apple_support" if identifier_evidence else None,
        "performance_claim": False,
    }
    return existing
