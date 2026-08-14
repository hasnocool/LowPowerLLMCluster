from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit


_PREFIXES = {
    "aaeon": "AAEON",
    "seco": "SECO",
    "congatec": "congatec",
    "axiomtek": "Axiomtek",
    "lanner": "Lanner",
    "portwell": "Portwell",
    "kontron": "Kontron",
    "advantech": "Advantech",
    "premio": "Premio",
    "connecttech": "Connect Tech",
    "forecr": "Forecr",
    "auvidea": "Auvidea",
    "aetina": "Aetina",
    "waveshare": "Waveshare",
    "amd": "AMD",
    "digilent": "Digilent",
    "bittware": "BittWare",
    "radxa": "Radxa",
    "dfrobot": "DFRobot",
    "pine64": "PINE64",
    "raspberry-pi": "Raspberry Pi",
    "orange-pi": "Orange Pi",
    "framework": "Framework",
    "lenovo": "Lenovo",
    "dell": "Dell",
    "hp-": "HP",
    "minisforum": "MINISFORUM",
}

_DOMAINS = {
    "aaeon.com": "AAEON",
    "seco.com": "SECO",
    "congatec.com": "congatec",
    "axiomtek.com": "Axiomtek",
    "lannerinc.com": "Lanner",
    "portwell.com": "Portwell",
    "kontron.com": "Kontron",
    "advantech.com": "Advantech",
    "premioinc.com": "Premio",
    "connecttech.com": "Connect Tech",
    "forecr.io": "Forecr",
    "auvidea.eu": "Auvidea",
    "aetina.com": "Aetina",
    "waveshare.com": "Waveshare",
    "amd.com": "AMD",
    "digilent.com": "Digilent",
    "bittware.com": "BittWare",
    "radxa.com": "Radxa",
    "dfrobot.com": "DFRobot",
    "pine64.org": "PINE64",
    "raspberrypi.com": "Raspberry Pi",
    "orangepi.org": "Orange Pi",
    "frame.work": "Framework",
    "lenovo.com": "Lenovo",
    "dell.com": "Dell",
    "hp.com": "HP",
    "minisforum.com": "MINISFORUM",
}

_OFFICIAL_CLASSES = {
    "industrial_edge",
    "jetson_ecosystem",
    "fpga_accelerator",
    "vendor_release",
    "manufacturer",
    "official",
}

_CATEGORY_TOKENS = (
    "/category/", "/categories/", "/collections/", "/search", "/all-products", "/products/$",
    "/product-category/", "/blog/", "/news/", "/press/", "/support/", "/resources/",
)


def _host(url: str) -> str:
    value = (urlsplit(str(url)).hostname or "").lower()
    return value[4:] if value.startswith("www.") else value


def _domain_manufacturer(host: str) -> str:
    for domain, manufacturer in _DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return manufacturer
    return ""


def source_manufacturer(source: Mapping[str, Any] | None, *, source_name: str, listing_url: str) -> tuple[str, str]:
    cfg = source or {}
    explicit = str(cfg.get("manufacturer") or "").strip()
    if explicit:
        return explicit, "source_registry_explicit"
    name = source_name.strip().lower()
    for prefix, manufacturer in _PREFIXES.items():
        if name.startswith(prefix):
            return manufacturer, "source_registry_prefix"
    manufacturer = _domain_manufacturer(_host(listing_url))
    if manufacturer:
        return manufacturer, "official_domain"
    for seed in [cfg.get("endpoint"), *(cfg.get("seeds") or []), *(cfg.get("urls") or [])]:
        if seed:
            manufacturer = _domain_manufacturer(_host(str(seed)))
            if manufacturer:
                return manufacturer, "source_registry_domain"
    return "", ""


def _source_hosts(source: Mapping[str, Any] | None) -> set[str]:
    cfg = source or {}
    result: set[str] = set()
    for value in [cfg.get("endpoint"), *(cfg.get("seeds") or []), *(cfg.get("urls") or [])]:
        if value:
            host = _host(str(value))
            if host:
                result.add(host)
    return result


def official_product_url(record: Mapping[str, Any], source: Mapping[str, Any] | None = None) -> bool:
    url = str(record.get("listing_url") or "")
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False
    path = (parsed.path or "/").lower()
    if path in {"", "/"}:
        return False
    if any(token.rstrip("$") in path for token in _CATEGORY_TOKENS):
        return False
    cfg = source or {}
    source_class = str(cfg.get("source_class") or "").lower()
    host = _host(url)
    known_manufacturer = bool(_domain_manufacturer(host))
    same_as_seed = any(host == seed or host.endswith("." + seed) or seed.endswith("." + host) for seed in _source_hosts(cfg))
    product_hint = any(token in path for token in ("/product/", "/products/", "/detail", "/shop/", "/store/"))
    return bool((known_manufacturer or same_as_seed or source_class in _OFFICIAL_CLASSES) and product_hint)


def enrich_identity(record: Mapping[str, Any], source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = dict(record)
    raw = dict(value.get("raw_attributes") or {}) if isinstance(value.get("raw_attributes"), Mapping) else {}
    if not str(value.get("manufacturer") or "").strip():
        manufacturer, evidence = source_manufacturer(source, source_name=str(value.get("source") or ""), listing_url=str(value.get("listing_url") or ""))
        if manufacturer:
            value["manufacturer"] = manufacturer
            raw["manufacturer_evidence"] = {"type": evidence, "confidence": 0.98}
    if official_product_url(value, source):
        raw["official_product_url_identity"] = True
        raw["identity_evidence"] = "official_product_url"
    value["raw_attributes"] = raw
    return value
