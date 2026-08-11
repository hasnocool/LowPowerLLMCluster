from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from .catalog import project_root

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


async def enrich_candidate(component: str, candidate: dict[str, Any], config: dict[str, Any], *, client: httpx.AsyncClient) -> dict[str, Any]:
    listing = candidate.get("listing") or {}; association = associate_spec_source(component, listing, config)
    if association is None:
        candidate["spec_enrichment"] = {"status": "unassociated", "fields_added": 0}; return candidate
    url = str(association.get("source_url") or "")
    if not url.startswith("https://"):
        candidate["spec_enrichment"] = {"status": "invalid_source_url", "fields_added": 0, "association_id": association.get("id")}; return candidate
    observed_at = _now()
    try:
        response = await client.get(url); response.raise_for_status()
    except Exception as exc:
        candidate["spec_enrichment"] = {"status": "fetch_failed", "fields_added": 0, "association_id": association.get("id"), "source_url": url, "error": f"{type(exc).__name__}: {exc}"}; return candidate
    collector = _TextCollector(); collector.feed(response.text); text = " ".join(collector.chunks); verify_terms = [_norm(value) for value in association.get("verify_terms_any", []) if value]
    if verify_terms and not any(term in _norm(text) for term in verify_terms):
        candidate["spec_enrichment"] = {"status": "identity_not_verified", "fields_added": 0, "association_id": association.get("id"), "source_url": url}; return candidate
    facts, evidence = extract_spec_fields(text, association, url, observed_at); merged = dict(candidate.get("compatibility_facts") or {}); merged.update(facts); candidate["compatibility_facts"] = merged
    provenance = dict(candidate.get("compatibility_fact_provenance") or {}); provenance.update(evidence); candidate["compatibility_fact_provenance"] = provenance
    candidate["spec_enrichment"] = {"status": "enriched" if facts else "verified_no_fields_extracted", "fields_added": len(facts), "association_id": association.get("id"), "manufacturer": association.get("manufacturer"), "source_url": url, "observed_at": observed_at}
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
    target = evidence_path or project_root() / "data" / "market" / "spec-evidence.json"; payload = {"schema_version": 1, "generated_at": _now(), "records": evidence_rows}; _write(target, payload); return payload
