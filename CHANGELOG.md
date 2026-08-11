# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-08-10

### Added

- Automatic listing-time extraction of explicit SSD/NVMe controller, NAND type, storage interface, GPU board partner/revision/VBIOS, RAM topology, mobile SKU/SoC variant and accelerator host-context facts.
- Seller-stated PCB revision and currently installed BIOS/UEFI evidence for structured marketplace listings, retained below manufacturer evidence in confidence/authority.
- Revision-scoped BIOS history ingestion from official manufacturer BIOS API payloads when board/PCB revision metadata is explicitly present.
- `docs/AUTOMATIC_IDENTITY_ENRICHMENT.md` plus deterministic identity/firmware tests and governance.
- Exact Apple marketplace configuration resolution for A-number/model/part identity, M1-M5 chip family, installed unified memory, SSD/storage, screen size, and explicitly stated CPU/GPU core counts.
- Used-Apple condition evidence for battery cycle count, battery health, stated Activation Lock / Find My status, and MDM / Remote Management state without treating condition as SKU identity.
- Apple configuration enrichment in live manufacturer JSON-LD and eBay marketplace listings before catalog matching, price-history persistence, CAD landed-cost calculation and TCO analysis.
- Manufacturer CPU-support endpoint ingestion with bounded async pagination, provider-aware normalization for ASUS/MSI/Gigabyte-ASRock style support surfaces, and strict same-manufacturer host boundaries.
- Explicit CPU-support matrix completeness proofs from total-page count, total-row count, or `hasMore=false` metadata; static/short responses remain incomplete without proof.
- Structured motherboard enrichment can promote an explicitly complete API matrix, use a larger partial API matrix for better coverage, and refuses to let smaller partial responses erase stronger existing evidence.
- Asynchronous product-discovery adapter contract plus deterministic JSON feed importer.
- Live manufacturer JSON-LD discovery for public schema.org `Product` / `Offer` pages.
- Mouser Search API adapter using `MOUSER_API_KEY`.
- DigiKey Product Information V4 adapter using external OAuth credentials with CA/CAD locale defaults.
- eBay Browse API adapter using application OAuth and the Canadian marketplace for used/secondary-market discovery.
- Credential-free source configuration in `data/market/sources.json`; secrets remain environment-only.
- Normalized listing model and concurrent multi-source discovery with source/listing deduplication and per-source success/failure status.
- Append-only price observation history linked back to catalog part IDs.
- Exact-SKU/configuration confidence scoring that does not confuse CPU theoretical RAM limits with installed RAM.
- Independent seller/source confidence using source class plus marketplace feedback signals when available.
- Query-scope-aware `discovered`, `disappeared`, and `reappeared` listing lifecycle tracking.
- Automatic sourced CAD FX snapshots from the Bank of Canada Valet API with append-only FX history.
- Explicit Canadian landed-cost breakdown for item, shipping, duty, brokerage and tax.
- Sourced vendor/community performance ingestion requiring model, runtime, workload, metric, unit and source URL provenance.
- Strict compatible-performance aggregation that keeps different model variants, quantizations, runtime versions, workload phases, units, context dimensions and hardware configurations separate.

### Changed

- Every normalized listing now receives a conservative identity-enrichment pass that fills only missing explicit facts and never overwrites stronger structured evidence.
- Adaptive power matching can consume newly extracted storage silicon, GPU board/VBIOS/host context, RAM topology and mobile SKU/SoC identity.
- Manufacturer BIOS API probing now preserves revision-scoped rows separately from unscoped BIOS history.

