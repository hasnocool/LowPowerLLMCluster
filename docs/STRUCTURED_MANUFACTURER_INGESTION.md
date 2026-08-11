# Structured Manufacturer Document Ingestion

Exact product-page association is only the identity step. Once a manufacturer page is verified, compatibility facts should be extracted from the most structured evidence available before falling back to flattened prose.

## Evidence priority

```text
curated exact-SKU fields
  -> schema.org Product.additionalProperty
  -> HTML specification tables
  -> CPU / BIOS support matrices
  -> manufacturer PDF manuals / datasheets
  -> generic flattened-page text parser
  -> unresolved / unknown
```

The rule is field-by-field: a weaker source can fill a missing field, but it does not overwrite a value already supplied by a stronger verified source.

## Supported structured sources

### schema.org Product

`application/ld+json` blocks are parsed for `Product` nodes and `additionalProperty` / `PropertyValue` entries. Recognized labels can provide socket, DDR generation, PCIe facts, M.2 support, PSU wattage/connectors, case clearances, cooler height and exact GPU dimensions/power requirements.

### HTML specification tables

Real `<table>` rows are preserved as label/value pairs rather than flattened into a page-wide text string. This makes fields such as `Maximum GPU Length -> 360 mm` much less ambiguous than a generic regex over the whole page.

### CPU / BIOS support matrices

Motherboard support tables are inspected for CPU/model and BIOS columns. When a target CPU identity is available, the ingestion layer can record the matching CPU plus minimum BIOS version. This evidence is kept separately from broad socket compatibility: `AM4` alone is not proof that every AM4 CPU works on every BIOS.

### Manufacturer PDFs/manuals

Links that look like official manuals, datasheets, technical guides or specification PDFs may be followed when they remain on the verified manufacturer host. PDF text extraction uses `pypdf`; no OCR is performed. Only the first bounded set of likely documents and pages is considered. Parsed PDF facts rank below structured page data and above the flattened webpage fallback.

## Provenance

Each admitted field records:

- value;
- source URL;
- source type (`manufacturer_structured`, `manufacturer_support_table`, or `manufacturer_pdf`);
- observation timestamp;
- extraction method;
- association ID;
- identity score when available;
- confidence.

An enrichment record also reports counts for JSON-LD, table, support-matrix and PDF fields plus any PDF URLs used.

## Guardrails

- Structured ingestion only runs after the product/manufacturer association has already passed identity verification.
- PDF links must stay on the verified manufacturer host.
- JSON-LD and table labels are interpreted conservatively; unsupported fields remain unknown.
- A support-table BIOS result is tied to the target CPU row, not generalized to all processors on the socket.
- PDFs are text-extracted only; scanned/image-only manuals remain unresolved rather than triggering OCR.
- Structured evidence may reject a build when it exposes a real lane, BIOS, connector, power or clearance conflict.
- GPU family names still never inherit board-partner dimensions without exact/reference-board identity.

## Tests

`tests/test_structured_specs.py` covers schema.org property extraction, HTML spec tables, CPU/BIOS support matrices, manufacturer PDF-link filtering, structured precedence and field-level provenance.
