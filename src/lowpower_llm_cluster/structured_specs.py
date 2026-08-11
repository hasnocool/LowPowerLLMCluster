from __future__ import annotations

import io
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def _first_int(patterns: list[str], text: str, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = int(float(match.group(1)))
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        return value
    return None


def _merge(target: dict[str, Any], evidence: dict[str, Any], source: dict[str, Any], provenance: dict[str, Any]) -> None:
    # Structured sources are processed in priority order; first verified value wins.
    for field, value in source.items():
        if value is None or field in target:
            continue
        target[field] = value
        evidence[field] = {
            "value": value,
            **provenance,
        }


class StructuredHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jsonld: list[Any] = []
        self.tables: list[list[list[str]]] = []
        self.links: list[dict[str, str]] = []
        self._json_capture = False
        self._json_chunks: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_chunks: list[str] | None = None
        self._href: str | None = None
        self._link_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.casefold(): (v or "") for k, v in attrs}
        lower = tag.casefold()
        if lower == "script" and values.get("type", "").casefold() == "application/ld+json":
            self._json_capture = True
            self._json_chunks = []
        elif lower == "table":
            self._table = []
        elif lower == "tr" and self._table is not None:
            self._row = []
        elif lower in {"td", "th"} and self._row is not None:
            self._cell_chunks = []
        elif lower == "a" and values.get("href"):
            self._href = values["href"]
            self._link_chunks = []

    def handle_data(self, data: str) -> None:
        if self._json_capture:
            self._json_chunks.append(data)
        if self._cell_chunks is not None:
            self._cell_chunks.append(data)
        if self._href is not None:
            self._link_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.casefold()
        if lower == "script" and self._json_capture:
            self._json_capture = False
            raw = "".join(self._json_chunks).strip()
            if raw:
                try:
                    self.jsonld.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        elif lower in {"td", "th"} and self._cell_chunks is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell_chunks).split()))
            self._cell_chunks = None
        elif lower == "tr" and self._row is not None and self._table is not None:
            if any(cell for cell in self._row):
                self._table.append(self._row)
            self._row = None
        elif lower == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None
        elif lower == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": " ".join("".join(self._link_chunks).split())})
            self._href = None
            self._link_chunks = []


def _jsonld_nodes(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        out: list[dict[str, Any]] = []
        for row in document:
            out.extend(_jsonld_nodes(row))
        return out
    if not isinstance(document, dict):
        return []
    out = [document]
    graph = document.get("@graph")
    if isinstance(graph, list):
        out.extend(row for row in graph if isinstance(row, dict))
    return out


def _property_pairs(value: Any) -> list[tuple[str, str]]:
    rows = value if isinstance(value, list) else [value]
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("propertyID")
        val = row.get("value") or row.get("valueReference")
        if isinstance(val, dict):
            val = val.get("name") or val.get("value")
        if name is not None and val is not None:
            out.append((str(name), str(val)))
    return out


def parse_property_pairs(component: str, pairs: list[tuple[str, str]]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for key, value in pairs:
        label = _norm(key)
        text = str(value)
        lower = _norm(text)
        if component in {"cpu_host", "motherboard", "cooling"} and "socket" in label:
            sockets = [v for v in ("AM4", "AM5", "LGA1700", "LGA1851") if v.casefold() in lower]
            if component == "cooling" and sockets:
                facts["supported_sockets"] = sockets
            elif len(sockets) == 1:
                facts["socket"] = sockets[0]
        if component in {"cpu_host", "motherboard", "host_ram_32gb"} and any(term in label for term in ("memory type", "memory", "ddr")):
            types = [v for v in ("DDR4", "DDR5") if v.casefold() in lower]
            if component == "cpu_host" and types:
                facts["memory_types"] = types
            elif len(types) == 1:
                facts["memory_type"] = types[0]
        if component == "motherboard":
            if "form factor" in label:
                forms = [v for needle, v in (("e-atx", "E-ATX"), ("micro atx", "mATX"), ("matx", "mATX"), ("atx", "ATX"), ("mini itx", "Mini-ITX")) if needle in lower]
                if forms:
                    facts["form_factors"] = list(dict.fromkeys(forms))
            if "m.2" in label or "m2" in label:
                facts["supports_nvme_m2"] = True
                count = _first_int([r"(\d+)\s*x?\s*M\.2", r"M\.2\s*[x×]?\s*(\d+)"], text, minimum=1, maximum=8)
                if count:
                    facts["m2_slots"] = count
            if "pcie" in label or "pci express" in label:
                if "x16" in lower:
                    facts["gpu_slot"] = "PCIe x16"
                gen = _first_int([r"(?:PCIe|PCI Express)\s*(\d)(?:\.0)?"], text, minimum=3, maximum=6)
                if gen:
                    facts["pcie_generation"] = gen
                lanes = _first_int([r"x16[^0-9]{0,12}x(\d{1,2})", r"x(\d{1,2})\s+mode"], text, minimum=1, maximum=16)
                if lanes:
                    facts["gpu_slot_lanes"] = lanes
            if any(term in label for term in ("share", "lane", "m.2", "pcie")) and any(term in lower for term in ("unavailable", "disabled", "shares bandwidth", "share")):
                facts["lane_sharing_note"] = text.strip()
        elif component == "psu_750w":
            if any(term in label for term in ("wattage", "total power", "continuous power")):
                watts = _first_int([r"(\d{3,4})\s*W"], text, minimum=300, maximum=2000)
                if watts:
                    facts["wattage_w"] = watts
            if "connector" in label or "cable" in label:
                connectors: list[str] = []
                if any(term in lower for term in ("12v-2x6", "12vhpwr")):
                    connectors.append("12V-2x6")
                if any(term in lower for term in ("8 pin", "8-pin", "6+2")):
                    connectors.append("8-pin")
                if connectors:
                    facts["gpu_power_connectors"] = sorted(set(connectors))
        elif component == "chassis":
            if "gpu" in label or "graphics card" in label:
                length = _first_int([r"(\d{3})\s*mm"], text, minimum=150, maximum=700)
                if length:
                    facts["max_gpu_length_mm"] = length
            if "cooler" in label:
                height = _first_int([r"(\d{2,3})\s*mm"], text, minimum=35, maximum=250)
                if height:
                    facts["max_cpu_cooler_height_mm"] = height
            if "psu" in label and "length" in label:
                length = _first_int([r"(\d{2,3})\s*mm"], text, minimum=80, maximum=400)
                if length:
                    facts["max_psu_length_mm"] = length
        elif component == "cooling" and "height" in label:
            height = _first_int([r"(\d{2,3})\s*mm"], text, minimum=20, maximum=250)
            if height:
                facts["height_mm"] = height
        elif component in {"gpu", "gpu_accelerator"}:
            if any(term in label for term in ("length", "dimension")):
                length = _first_int([r"(\d{3})\s*mm"], text, minimum=100, maximum=600)
                if length:
                    facts["gpu_length_mm"] = length
            if "slot" in label:
                slots = _first_int([r"(\d)\s*[- ]?slot"], text, minimum=1, maximum=5)
                if slots:
                    facts["gpu_slots"] = slots
            if any(term in label for term in ("recommended psu", "power supply", "system power")):
                watts = _first_int([r"(\d{3,4})\s*W"], text, minimum=300, maximum=2000)
                if watts:
                    facts["minimum_psu_w"] = watts
            if "connector" in label:
                connectors: list[str] = []
                if any(term in lower for term in ("12v-2x6", "12vhpwr")):
                    connectors.append("12V-2x6")
                if any(term in lower for term in ("8 pin", "8-pin", "6+2")):
                    connectors.append("8-pin")
                if connectors:
                    facts["power_connectors"] = sorted(set(connectors))
    return facts


def extract_jsonld_facts(component: str, documents: list[Any]) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    for document in documents:
        for node in _jsonld_nodes(document):
            node_type = node.get("@type")
            types = {node_type} if isinstance(node_type, str) else set(node_type or [])
            if "Product" not in types:
                continue
            pairs.extend(_property_pairs(node.get("additionalProperty")))
    return parse_property_pairs(component, pairs)


def extract_table_facts(component: str, tables: list[list[list[str]]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    pairs: list[tuple[str, str]] = []
    support_rows: list[dict[str, str]] = []
    for table in tables:
        for row in table:
            if len(row) >= 2:
                pairs.append((row[0], " | ".join(row[1:])))
            joined = " | ".join(row)
            if component == "motherboard" and any(term in _norm(joined) for term in ("bios", "cpu", "processor")) and len(row) >= 2:
                support_rows.append({"cells": joined})
    return parse_property_pairs(component, pairs), support_rows


def extract_cpu_support_matrix(tables: list[list[list[str]]], target_cpu: str | None = None) -> dict[str, Any]:
    target = _norm(target_cpu)
    for table in tables:
        if not table:
            continue
        headers = [_norm(cell) for cell in table[0]]
        cpu_idx = next((i for i, cell in enumerate(headers) if any(term in cell for term in ("cpu", "processor", "model"))), None)
        bios_idx = next((i for i, cell in enumerate(headers) if "bios" in cell), None)
        if cpu_idx is None or bios_idx is None:
            continue
        for row in table[1:]:
            if len(row) <= max(cpu_idx, bios_idx):
                continue
            cpu_name = row[cpu_idx]
            if target and target not in _norm(cpu_name):
                continue
            return {"cpu_support_model": cpu_name, "minimum_bios_version": row[bios_idx]}
    return {}


def find_document_links(parser: StructuredHTMLParser, base_url: str) -> list[str]:
    out: list[str] = []
    for link in parser.links:
        href = urljoin(base_url, link.get("href") or "")
        text = _norm(link.get("text"))
        path = (urlparse(href).path or "").casefold()
        if path.endswith(".pdf") and any(term in text + " " + path for term in ("manual", "datasheet", "spec", "guide", "technical")):
            out.append(href)
    return list(dict.fromkeys(out))


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:80])
    except Exception:
        return ""


async def ingest_structured_manufacturer_document(
    component: str,
    html: str,
    source_url: str,
    observed_at: str,
    association_id: str,
    identity_score: float | None,
    *,
    client: httpx.AsyncClient | None = None,
    target_cpu: str | None = None,
    allowed_host: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    parser = StructuredHTMLParser()
    parser.feed(html)
    facts: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    stats: dict[str, Any] = {"jsonld_fields": 0, "table_fields": 0, "support_fields": 0, "pdf_fields": 0, "pdf_urls": []}

    jsonld = extract_jsonld_facts(component, parser.jsonld)
    _merge(facts, evidence, jsonld, {"source_url": source_url, "source_type": "manufacturer_structured", "observed_at": observed_at, "extraction": "schema_org_additionalProperty", "association_id": association_id, "identity_score": identity_score, "confidence": "exact" if identity_score and identity_score >= 0.9 else "high"})
    stats["jsonld_fields"] = len(jsonld)

    table_facts, _ = extract_table_facts(component, parser.tables)
    _merge(facts, evidence, table_facts, {"source_url": source_url, "source_type": "manufacturer_structured", "observed_at": observed_at, "extraction": "html_spec_table", "association_id": association_id, "identity_score": identity_score, "confidence": "exact" if identity_score and identity_score >= 0.9 else "high"})
    stats["table_fields"] = len(table_facts)

    if component == "motherboard":
        support = extract_cpu_support_matrix(parser.tables, target_cpu=target_cpu)
        _merge(facts, evidence, support, {"source_url": source_url, "source_type": "manufacturer_support_table", "observed_at": observed_at, "extraction": "cpu_bios_support_matrix", "association_id": association_id, "identity_score": identity_score, "confidence": "exact" if target_cpu else "high"})
        stats["support_fields"] = len(support)

    if client is not None:
        links = find_document_links(parser, source_url)[:3]
        source_host = (urlparse(source_url).hostname or "").casefold()
        allowed = (allowed_host or source_host).casefold()
        for pdf_url in links:
            host = (urlparse(pdf_url).hostname or "").casefold()
            if not (host == allowed or host.endswith("." + allowed)):
                continue
            try:
                response = await client.get(pdf_url)
                response.raise_for_status()
                if "pdf" not in str(response.headers.get("content-type", "")).casefold() and not pdf_url.casefold().endswith(".pdf"):
                    continue
                text = extract_pdf_text(response.content)
            except Exception:
                continue
            if not text:
                continue
            pdf_facts = parse_property_pairs(component, [("manual", text[:50000])])
            # For PDF prose, augment with component-specific regexes where a label/value table was flattened.
            if component in {"gpu", "gpu_accelerator"}:
                length = _first_int([r"(?:card length|length|dimensions)[^0-9]{0,30}(\d{3})\s*mm"], text, minimum=100, maximum=600)
                if length:
                    pdf_facts.setdefault("gpu_length_mm", length)
                psu = _first_int([r"(?:recommended|minimum)[^\n]{0,30}(?:psu|power supply|system power)[^0-9]{0,20}(\d{3,4})\s*w"], text, minimum=300, maximum=2000)
                if psu:
                    pdf_facts.setdefault("minimum_psu_w", psu)
            elif component == "chassis":
                length = _first_int([r"(?:gpu|graphics card)[^\n]{0,30}(?:clearance|length)[^0-9]{0,20}(\d{3})\s*mm"], text, minimum=150, maximum=700)
                if length:
                    pdf_facts.setdefault("max_gpu_length_mm", length)
            elif component == "cooling":
                height = _first_int([r"(?:height|dimensions)[^0-9]{0,25}(\d{2,3})\s*mm"], text, minimum=20, maximum=250)
                if height:
                    pdf_facts.setdefault("height_mm", height)
            _merge(facts, evidence, pdf_facts, {"source_url": pdf_url, "source_type": "manufacturer_pdf", "observed_at": observed_at, "extraction": "pdf_text", "association_id": association_id, "identity_score": identity_score, "confidence": "high"})
            stats["pdf_fields"] += len(pdf_facts)
            stats["pdf_urls"].append(pdf_url)

    return facts, evidence, stats
