from __future__ import annotations

import asyncio

from lowpower_llm_cluster.structured_specs import (
    StructuredHTMLParser,
    extract_cpu_support_matrix,
    extract_cpu_support_rows,
    extract_jsonld_facts,
    extract_table_facts,
    find_document_links,
    ingest_structured_manufacturer_document,
)


def test_schema_org_additional_property_extracts_gpu_specs() -> None:
    documents = [{
        "@type": "Product",
        "name": "Example GPU",
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "Card Length", "value": "320 mm"},
            {"@type": "PropertyValue", "name": "Recommended PSU", "value": "750 W"},
            {"@type": "PropertyValue", "name": "Power Connector", "value": "1x 12V-2x6"},
        ],
    }]
    facts = extract_jsonld_facts("gpu", documents)
    assert facts["gpu_length_mm"] == 320
    assert facts["minimum_psu_w"] == 750
    assert facts["power_connectors"] == ["12V-2x6"]


def test_html_spec_table_extracts_case_clearances() -> None:
    html = """
    <table>
      <tr><th>Specification</th><th>Value</th></tr>
      <tr><td>Maximum GPU Length</td><td>360 mm</td></tr>
      <tr><td>Maximum CPU Cooler Height</td><td>170 mm</td></tr>
      <tr><td>Maximum PSU Length</td><td>220 mm</td></tr>
    </table>
    """
    parser = StructuredHTMLParser(); parser.feed(html)
    facts, _ = extract_table_facts("chassis", parser.tables)
    assert facts["max_gpu_length_mm"] == 360
    assert facts["max_cpu_cooler_height_mm"] == 170
    assert facts["max_psu_length_mm"] == 220


def test_cpu_support_table_extracts_minimum_bios_and_rows() -> None:
    tables = [[
        ["CPU Model", "Core", "BIOS"],
        ["Ryzen 5 5600", "Vermeer", "7C56vA9"],
        ["Ryzen 7 5700X", "Vermeer", "7C56vAB"],
    ]]
    facts = extract_cpu_support_matrix(tables, target_cpu="Ryzen 5 5600")
    assert facts["cpu_support_model"] == "Ryzen 5 5600"
    assert facts["minimum_bios_version"] == "7C56vA9"
    assert facts["cpu_support_status"] == "supported"
    rows = extract_cpu_support_rows(tables)
    assert len(rows) == 2
    assert rows[0]["support_status"] == "supported"


def test_cpu_support_table_preserves_explicit_unsupported_status() -> None:
    tables = [[
        ["Processor", "BIOS", "Status"],
        ["Ryzen 5 5600", "7C56vA9", "Supported"],
        ["Ryzen 9 5950X", "N/A", "Unsupported"],
    ]]
    rows = extract_cpu_support_rows(tables)
    assert rows[1]["cpu_model"] == "Ryzen 9 5950X"
    assert rows[1]["support_status"] == "unsupported"


def test_manual_pdf_links_are_bounded_to_document_like_links() -> None:
    html = """
      <a href="/manuals/board-manual.pdf">User Manual</a>
      <a href="/marketing/brochure.pdf">Pretty brochure</a>
      <a href="/support/specification-guide.pdf">Technical Guide</a>
    """
    parser = StructuredHTMLParser(); parser.feed(html)
    links = find_document_links(parser, "https://vendor.example/product")
    assert links == [
        "https://vendor.example/manuals/board-manual.pdf",
        "https://vendor.example/support/specification-guide.pdf",
    ]


def test_structured_ingestion_precedence_provenance_and_matrix_retention() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"Product","additionalProperty":[
      {"@type":"PropertyValue","name":"Socket","value":"AM4"},
      {"@type":"PropertyValue","name":"Memory Type","value":"DDR4"}
    ]}
    </script>
    <table>
      <tr><td>Form Factor</td><td>ATX</td></tr>
      <tr><td>M.2 Slots</td><td>2 x M.2 NVMe</td></tr>
      <tr><td>PCIe Slot</td><td>PCIe 4.0 x16 (x16 mode)</td></tr>
    </table>
    <table>
      <tr><th>CPU Model</th><th>BIOS</th></tr>
      <tr><td>Ryzen 5 5600</td><td>7C56vA9</td></tr>
    </table>
    """
    facts, evidence, stats = asyncio.run(ingest_structured_manufacturer_document(
        "motherboard", html, "https://vendor.example/board", "2026-08-11T00:00:00+00:00", "auto:Vendor:BOARD1", 0.95
    ))
    assert facts["socket"] == "AM4"
    assert facts["memory_type"] == "DDR4"
    assert facts["form_factors"] == ["ATX"]
    assert facts["supports_nvme_m2"] is True
    assert facts["pcie_generation"] == 4
    assert evidence["socket"]["extraction"] == "schema_org_additionalProperty"
    assert evidence["form_factors"]["extraction"] == "html_spec_table"
    assert stats["jsonld_fields"] >= 2
    assert stats["table_fields"] >= 2
    assert stats["cpu_support_matrix"][0]["cpu_model"] == "Ryzen 5 5600"
    assert stats["cpu_support_matrix"][0]["minimum_bios_version"] == "7C56vA9"
    assert stats["cpu_support_matrix"][0]["source_type"] == "manufacturer_support_table"
    assert stats["cpu_support_matrix_complete"] is False
