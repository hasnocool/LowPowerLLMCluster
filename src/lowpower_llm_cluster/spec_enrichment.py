from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from .catalog import project_root
from .manufacturer_discovery import discover_manufacturer_association

USER_AGENT = "LowPowerLLMCluster/0.5 (+https://github.com/hasnocool/LowPowerLLMCluster)"


def _now() -> str: return datetime.now(UTC).isoformat()

def _load(path: Path, default: Any) -> Any:
    if not path.exists(): return default
    return json.loads(path.read_text(encoding="utf-8"))

def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); tmp.replace(path)

def _norm(value: Any) -> str: return " ".join(str(value or "").casefold().replace("-", " ").split())


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self._skip = 0; self.chunks: list[str] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"}: self._skip += 1
    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"} and self._skip: self._skip -= 1
    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip(): self.chunks.append(data.strip())


def _page_text(html: str) -> str:
    collector = _TextCollector(); collector.feed(html); return " ".join(collector.chunks)


def load_spec_enrichment_config(path: Path | None = None) -> dict[str, Any]:
    return _load(path or project_root() / "data" / "market" / "spec-enrichment.json", {"schema_version": 1, "associations": []})


def associate_spec_source(component: str, listing: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    title = _norm(listing.get("title")); sku = _norm(listing.get("sku")); haystack = f"{title} {sku}".strip(); matches: list[tuple[int, dict[str, Any]]] = []
    for association in config.get("associations", []):
        if association.get("component") != component: continue
        exact_skus = [_norm(value) for value in association.get("exact_skus", []) if value]; match_terms = [_norm(value) for value in association.get("match_terms", []) if value]
        exact = bool(sku and exact_skus and sku in exact_skus); term_hits = sum(1 for term in match_terms if term in haystack)
        if exact or term_hits: matches.append((100 if exact else term_hits, association))
    if not matches: return None
    matches.sort(key=lambda row: row[0], reverse=True); return dict(matches[0][1])


def _cast(value: str, kind: str) -> Any:
    if kind == "int": return int(float(value))
    if kind == "float": return float(value)
    if kind == "bool": return value.strip().casefold() in {"1", "true", "yes", "supported"}
    return value.strip()


def extract_spec_fields(text: str, association: dict[str, Any], source_url: str, observed_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    facts: dict[str, Any] = {}; evidence: dict[str, Any] = {}; normalized = " ".join(text.split())
    for field, rule in (association.get("fields") or {}).items():
        value: Any = None; extraction = None
        if "regex" in rule:
            match = re.search(str(rule["regex"]), normalized, re.IGNORECASE)
            if match: value = _cast(match.group(int(rule.get("group", 1))), str(rule.get("cast", "str"))); extraction = "manufacturer_page_regex"
        elif "constant" in rule:
            value = rule["constant"]; extraction = "verified_manufacturer_page_constant"
        elif "contains" in rule:
            found = [out for needle, out in rule["contains"].items() if _norm(needle) in _norm(normalized)]
            if found: value = found if rule.get("many", False) else found[0]; extraction = "manufacturer_page_contains"
        if value is None: continue
        facts[field] = value; evidence[field] = {"value": value, "source_url": source_url, "source_type": "manufacturer_spec", "observed_at": observed_at, "extraction": extraction, "confidence": "exact" if association.get("exact_skus") else "high", "association_id": association.get("id")}
    return facts, evidence


def _first_int(patterns: list[str], text: str, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match: continue
        value = int(float(match.group(1)))
        if minimum is not None and value < minimum: continue
        if maximum is not None and value > maximum: continue
        return value
    return None


def _auto_fact_evidence(facts: dict[str, Any], source_url: str, observed_at: str, association_id: str, identity_score: float | None) -> dict[str, Any]:
    confidence = "exact" if identity_score is not None and identity_score >= 0.9 else "high"
    return {field: {"value": value, "source_url": source_url, "source_type": "manufacturer_spec", "observed_at": observed_at, "extraction": "automatic_manufacturer_page_parser", "confidence": confidence, "association_id": association_id, "identity_score": identity_score} for field, value in facts.items()}


def extract_automatic_spec_fields(component: str, text: str, source_url: str, observed_at: str, association_id: str, identity_score: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Conservative generic parser for automatically associated official product pages."""
    raw = " ".join(text.split())
    lower = raw.casefold()
    facts: dict[str, Any] = {}

    if component in {"cpu_host", "motherboard", "cooling"}:
        socket_hits = [value for value in ("AM4", "AM5", "LGA1700", "LGA1851") if value.casefold() in lower]
        if component != "cooling" and len(socket_hits) == 1:
            facts["socket"] = socket_hits[0]
        elif component == "cooling" and socket_hits:
            facts["supported_sockets"] = socket_hits

    if component in {"cpu_host", "motherboard", "host_ram_32gb"}:
        memories = [value for value in ("DDR4", "DDR5") if value.casefold() in lower]
        if component == "cpu_host" and memories:
            facts["memory_types"] = memories
        elif component in {"motherboard", "host_ram_32gb"} and len(memories) == 1:
            facts["memory_type"] = memories[0]

    if component == "cpu_host":
        generation = _first_int([r"PCIe\s*(?:Gen(?:eration)?\s*)?(\d)(?:\.0)?", r"PCI Express\s*(\d)(?:\.0)?"], raw, minimum=3, maximum=6)
        if generation: facts["pcie_generation"] = generation
        tdp = _first_int([r"(?:Processor Base Power|TDP|Default TDP)[^0-9]{0,25}(\d{2,3})\s*W"], raw, minimum=15, maximum=400)
        if tdp: facts["tdp_w"] = tdp

    elif component == "motherboard":
        if "atx" in lower:
            forms: list[str] = []
            if re.search(r"\b(?:micro[- ]?atx|matx|m-atx)\b", lower): forms.append("mATX")
            if re.search(r"\batx\b", lower) and not forms: forms.append("ATX")
            if forms: facts["form_factors"] = forms
        if re.search(r"PCI(?:e| Express)[^\n]{0,40}x16", raw, re.IGNORECASE): facts["gpu_slot"] = "PCIe x16"
        lanes = _first_int([r"PCI(?:e| Express)[^\n]{0,50}x16[^\n]{0,25}x(\d{1,2})", r"x16[^\n]{0,25}\(x(\d{1,2})\s+mode\)"], raw, minimum=1, maximum=16)
        if lanes: facts["gpu_slot_lanes"] = lanes
        generation = _first_int([r"PCIe\s*(?:Gen(?:eration)?\s*)?(\d)(?:\.0)?\s*x16", r"PCI Express\s*(\d)(?:\.0)?\s*x16"], raw, minimum=3, maximum=6)
        if generation: facts["pcie_generation"] = generation
        m2_hits = len(re.findall(r"\bM\.2\b", raw, re.IGNORECASE))
        if m2_hits: facts["supports_nvme_m2"] = True; facts["m2_slots"] = min(m2_hits, 8)
        share_match = re.search(r"([^.!?]{0,120}(?:unavailable|disabled|shares? bandwidth|share[^.!?]{0,30}lanes?)[^.!?]{0,120})", raw, re.IGNORECASE)
        if share_match: facts["lane_sharing_note"] = share_match.group(1).strip()

    elif component == "psu_750w":
        watts = _first_int([r"(?:Total Power|Continuous Power|Wattage|Power)[^0-9]{0,20}(\d{3,4})\s*W", r"\b(\d{3,4})\s*W\b"], raw, minimum=300, maximum=2000)
        if watts: facts["wattage_w"] = watts
        if "atx 3.1" in lower: facts["atx_standard"] = "ATX 3.1"
        elif "atx 3.0" in lower: facts["atx_standard"] = "ATX 3.0"
        connectors: list[str] = []
        if any(token in lower for token in ("12v-2x6", "12v 2x6", "12vhpwr")): connectors.append("12V-2x6")
        if any(token in lower for token in ("6+2", "6 + 2", "8-pin pcie", "8 pin pcie")): connectors.append("8-pin")
        if connectors: facts["gpu_power_connectors"] = sorted(set(connectors))
        high_power = _first_int([r"12V[- ]?2x6[^0-9]{0,40}(\d{3,4})\s*W", r"12VHPWR[^0-9]{0,40}(\d{3,4})\s*W"], raw, minimum=300, maximum=700)
        if high_power: facts["native_12v2x6_w"] = high_power

    elif component == "chassis":
        gpu = _first_int([r"(?:Maximum|Max\.?)[^\n]{0,25}(?:GPU|Graphics Card)[^0-9]{0,25}(\d{3})\s*mm", r"GPU[^\n]{0,25}(?:Length|Clearance)[^0-9]{0,25}(\d{3})\s*mm"], raw, minimum=150, maximum=700)
        cooler = _first_int([r"(?:Maximum|Max\.?)[^\n]{0,25}(?:CPU )?Cooler[^0-9]{0,25}(\d{2,3})\s*mm", r"CPU Cooler[^\n]{0,25}(?:Height|Clearance)[^0-9]{0,25}(\d{2,3})\s*mm"], raw, minimum=35, maximum=250)
        psu = _first_int([r"(?:Maximum|Max\.?)[^\n]{0,25}PSU[^0-9]{0,25}(\d{2,3})\s*mm"], raw, minimum=80, maximum=400)
        if gpu: facts["max_gpu_length_mm"] = gpu
        if cooler: facts["max_cpu_cooler_height_mm"] = cooler
        if psu: facts["max_psu_length_mm"] = psu
        forms = []
        for needle, value in ((r"\bE-ATX\b", "E-ATX"), (r"\bATX\b", "ATX"), (r"\b(?:Micro[- ]?ATX|mATX)\b", "mATX"), (r"\bMini[- ]?ITX\b", "Mini-ITX")):
            if re.search(needle, raw, re.IGNORECASE): forms.append(value)
        if forms: facts["motherboard_form_factors"] = list(dict.fromkeys(forms))
        slots = _first_int([r"(?:Expansion Slots|Horizontal Slots)[^0-9]{0,20}(\d{1,2})"], raw, minimum=1, maximum=16)
        if slots: facts["max_gpu_slots"] = slots

    elif component == "cooling":
        height = _first_int([r"(?:Height|Product Height)[^0-9]{0,25}(\d{2,3})\s*mm"], raw, minimum=20, maximum=250)
        if height: facts["height_mm"] = height

    elif component in {"gpu", "gpu_accelerator"}:
        gpu_length = _first_int([r"(?:Length|Card Length|Graphics Card Dimensions)[^0-9]{0,30}(\d{3})\s*mm", r"(\d{3})\s*mm\s*[x×]\s*\d{2,3}\s*mm"], raw, minimum=100, maximum=600)
        if gpu_length: facts["gpu_length_mm"] = gpu_length
        slots = _first_int([r"(?:Slot|Slots|Slot Width)[^0-9]{0,15}(\d(?:\.\d)?)\s*(?:slot|slots)?"], raw, minimum=1, maximum=5)
        if slots: facts["gpu_slots"] = slots
        psu = _first_int([r"(?:Recommended|Minimum|Required)[^\n]{0,30}(?:System )?(?:Power|PSU)[^0-9]{0,25}(\d{3,4})\s*W", r"(?:Power Supply|System Power)[^0-9]{0,25}(\d{3,4})\s*W"], raw, minimum=300, maximum=2000)
        if psu: facts["minimum_psu_w"] = psu
        connectors = []
        if any(token in lower for token in ("12v-2x6", "12v 2x6", "12vhpwr")): connectors.append("12V-2x6")
        if any(token in lower for token in ("8-pin", "8 pin", "8pin")): connectors.append("8-pin")
        if connectors: facts["power_connectors"] = sorted(set(connectors))
        lane_match = re.search(r"PCI(?:e| Express)\s*(?:Gen\s*)?(\d)(?:\.0)?\s*x(\d{1,2})", raw, re.IGNORECASE)
        if lane_match: facts["pcie_generation"] = int(lane_match.group(1)); facts["minimum_pcie_lanes"] = int(lane_match.group(2)); facts["pcie_slot"] = "x16" if int(lane_match.group(2)) <= 16 else f"x{lane_match.group(2)}"
        if "resizable bar" in lower or "rebar" in lower: facts["resizable_bar_required"] = "required" in lower or "must" in lower

    return facts, _auto_fact_evidence(facts, source_url, observed_at, association_id, identity_score)


async def _fetch_verified_page(association: dict[str, Any], client: httpx.AsyncClient) -> tuple[str | None, str | None]:
    url = str(association.get("source_url") or "")
    if not url.startswith("https://"): return None, "invalid_source_url"
    page_html = association.pop("page_html", None)
    if page_html is not None: return str(page_html), None
    try:
        response = await client.get(url); response.raise_for_status(); return response.text, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


async def enrich_candidate(component: str, candidate: dict[str, Any], config: dict[str, Any], *, client: httpx.AsyncClient) -> dict[str, Any]:
    listing = candidate.get("listing") or {}; association = associate_spec_source(component, listing, config); automatic = False
    if association is None and bool(config.get("automatic_discovery", {}).get("enabled", True)):
        association = await discover_manufacturer_association(component, listing, client=client)
        automatic = association is not None
    if association is None:
        candidate["spec_enrichment"] = {"status": "unassociated", "fields_added": 0}; return candidate
    url = str(association.get("source_url") or ""); observed_at = _now(); page_html, fetch_error = await _fetch_verified_page(association, client)
    if page_html is None:
        candidate["spec_enrichment"] = {"status": "fetch_failed" if fetch_error != "invalid_source_url" else "invalid_source_url", "fields_added": 0, "association_id": association.get("id") or association.get("mpn"), "source_url": url, "error": fetch_error}; return candidate
    text = _page_text(page_html)
    if not automatic:
        verify_terms = [_norm(value) for value in association.get("verify_terms_any", []) if value]
        if verify_terms and not any(term in _norm(text) for term in verify_terms):
            candidate["spec_enrichment"] = {"status": "identity_not_verified", "fields_added": 0, "association_id": association.get("id"), "source_url": url}; return candidate
        facts, evidence = extract_spec_fields(text, association, url, observed_at)
        association_id = str(association.get("id") or "curated")
        manufacturer = association.get("manufacturer")
        identity_score = 1.0 if association.get("exact_skus") else None
    else:
        association_id = "auto:" + str(association.get("manufacturer") or "unknown") + ":" + str(association.get("mpn") or "unknown")
        facts, evidence = extract_automatic_spec_fields(component, text, url, observed_at, association_id, association.get("identity_score"))
        manufacturer = association.get("manufacturer")
        identity_score = association.get("identity_score")
    merged = dict(candidate.get("compatibility_facts") or {}); merged.update(facts); candidate["compatibility_facts"] = merged
    provenance = dict(candidate.get("compatibility_fact_provenance") or {}); provenance.update(evidence); candidate["compatibility_fact_provenance"] = provenance
    candidate["spec_enrichment"] = {"status": "enriched" if facts else "verified_no_fields_extracted", "fields_added": len(facts), "association_id": association_id, "manufacturer": manufacturer, "source_url": url, "observed_at": observed_at, "association_origin": "automatic" if automatic else "curated", "identity_score": identity_score, "cache_hit": association.get("cache_hit") if automatic else None}
    return candidate


async def enrich_market_candidate(component: str, candidate: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    config = load_spec_enrichment_config(config_path); timeout = float(config.get("timeout_seconds", 20.0))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        return await enrich_candidate(component, candidate, config, client=client)


async def enrich_bom_candidates(components: dict[str, Any], *, config_path: Path | None = None, evidence_path: Path | None = None) -> dict[str, Any]:
    config = load_spec_enrichment_config(config_path); timeout = float(config.get("timeout_seconds", 20.0)); evidence_rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for component, component_row in components.items():
            for candidate in component_row.get("candidates") or []:
                await enrich_candidate(component, candidate, config, client=client); enrichment = candidate.get("spec_enrichment") or {}
                if enrichment.get("status") == "enriched": evidence_rows.append({"component": component, "source_id": (candidate.get("listing") or {}).get("source_id"), "title": (candidate.get("listing") or {}).get("title"), "spec_enrichment": enrichment, "field_evidence": candidate.get("compatibility_fact_provenance") or {}})
    target = evidence_path or project_root() / "data" / "market" / "spec-evidence.json"; payload = {"schema_version": 2, "generated_at": _now(), "records": evidence_rows}; _write(target, payload); return payload
