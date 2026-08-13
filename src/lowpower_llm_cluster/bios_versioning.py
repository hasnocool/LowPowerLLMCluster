from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def manufacturer_from_source(source_url: str | None = None, provider: str | None = None) -> str:
    if provider:
        value = provider.casefold()
        if value in {"asus", "msi", "gigabyte", "asrock"}:
            return value
    host = (urlparse(source_url or "").hostname or "").casefold()
    if "asus." in host:
        return "asus"
    if "msi." in host:
        return "msi"
    if "gigabyte." in host or "aorus." in host:
        return "gigabyte"
    if "asrock." in host:
        return "asrock"
    return "generic"


def _cmp(left: tuple[Any, ...], right: tuple[Any, ...]) -> int:
    return (left > right) - (left < right)


def _msi_key(version: str) -> tuple[str, int] | None:
    value = version.strip().upper()
    match = re.fullmatch(r"([0-9A-Z]+?)V([0-9A-Z]+)", value)
    suffix = match.group(2) if match else value
    prefix = match.group(1) if match else ""
    if not re.fullmatch(r"[0-9A-Z]+", suffix):
        return None
    try:
        rank = int(suffix, 36)
    except ValueError:
        return None
    return prefix, rank


def _gigabyte_key(version: str) -> tuple[int, int, str] | None:
    match = re.fullmatch(r"F(\d+)([A-Z]?)", version.strip().upper())
    if not match:
        return None
    number = int(match.group(1))
    suffix = match.group(2)
    # For the same numeric release, an unsuffixed stable release sorts after lettered beta builds.
    stable = 1 if not suffix else 0
    return number, stable, suffix


def _asus_key(version: str) -> tuple[int, ...] | None:
    value = version.strip().upper()
    if re.fullmatch(r"\d{3,5}", value):
        return (int(value),)
    match = re.fullmatch(r"([A-Z]*)(\d+(?:\.\d+)*)", value)
    if not match:
        return None
    if match.group(1) not in {"", "BIOS"}:
        return None
    return tuple(int(v) for v in match.group(2).split("."))


def _asrock_key(version: str) -> tuple[str, tuple[int, ...]] | None:
    match = re.fullmatch(r"([A-Z]?)(\d+(?:\.\d+)*)", version.strip().upper())
    if not match:
        return None
    return match.group(1), tuple(int(v) for v in match.group(2).split("."))


def compare_bios_versions(current: str | None, required: str | None, *, manufacturer: str = "generic") -> dict[str, Any]:
    """Compare BIOS versions only with manufacturer-specific semantics known to be safe.

    Returns relation=-1/0/1 for older/equal/newer, or relation=None when ordering cannot
    be established conservatively.
    """
    if not current or not required:
        return {"relation": None, "comparable": False, "reason": "missing_version", "manufacturer": manufacturer}
    if current.casefold() == required.casefold():
        return {"relation": 0, "comparable": True, "reason": "exact_version_match", "manufacturer": manufacturer}

    vendor = manufacturer.casefold()
    if vendor == "msi":
        left, right = _msi_key(current), _msi_key(required)
        if left and right and left[0] == right[0]:
            return {"relation": _cmp((left[1],), (right[1],)), "comparable": True, "reason": "msi_base36_suffix_order", "manufacturer": vendor}
    elif vendor == "gigabyte":
        left, right = _gigabyte_key(current), _gigabyte_key(required)
        if left and right:
            return {"relation": _cmp(left, right), "comparable": True, "reason": "gigabyte_f_release_order", "manufacturer": vendor}
    elif vendor == "asus":
        left, right = _asus_key(current), _asus_key(required)
        if left and right:
            return {"relation": _cmp(left, right), "comparable": True, "reason": "asus_numeric_release_order", "manufacturer": vendor}
    elif vendor == "asrock":
        left, right = _asrock_key(current), _asrock_key(required)
        if left and right and left[0] == right[0]:
            return {"relation": _cmp(left[1], right[1]), "comparable": True, "reason": "asrock_same_series_numeric_order", "manufacturer": vendor}

    return {"relation": None, "comparable": False, "reason": "vendor_version_order_unresolved", "manufacturer": vendor}


def shipped_bios_meets_requirement(current: str | None, required: str | None, *, source_url: str | None = None, provider: str | None = None) -> dict[str, Any]:
    manufacturer = manufacturer_from_source(source_url, provider)
    comparison = compare_bios_versions(current, required, manufacturer=manufacturer)
    relation = comparison.get("relation")
    comparison["meets_minimum"] = None if relation is None else relation >= 0
    comparison["current"] = current
    comparison["required"] = required
    return comparison
