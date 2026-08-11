# Automatic Identity Enrichment

This layer extracts explicit hardware identity facts as early as possible, before price matching, learned power aggregation, TCO or recommendation scoring.

## Source normalization

Every normalized `Listing` receives a conservative identity pass that may fill missing explicit fields for:

- SSD/NVMe controller, NAND type/revision, interface and capacity context;
- GPU board partner, PCB/board revision and VBIOS;
- RAM module count, per-module capacity, channel count and memory type;
- mobile device SKU, model, SoC and SoC variant;
- accelerator host CPU, motherboard, PSU and RAM context.

The preferred input is now structured source data rather than prose. The source adapters normalize schema.org `Product.additionalProperty`, DigiKey parameter arrays, Mouser/distributor attribute/specification arrays, and eBay localized aspects through `structured_identity.py`. Marketplace short descriptions are included in the lower-priority text pass where the source API exposes them.

Structured source fields always win. Text extraction only fills missing values and never invents controller silicon, NAND, PCB revisions, VBIOS, GPU bins, DIMM topology, or SoC variants from a family/product name.

## Manufacturer enrichment

Verified manufacturer product pages feed the same structured identity vocabulary. JSON-LD `additionalProperty` and HTML specification-table key/value rows are normalized before the generic flattened-page fallback. These structured identity facts are stored with manufacturer provenance and can narrow adaptive power identities through the candidate's verified `compatibility_facts`.

Examples of useful structured labels include:

```text
SSD Controller       → Phison E18
NAND Type            → Micron 176L TLC
PCB Revision         → B1
VBIOS Version        → 94.02.42.00.F0
Memory Configuration → 2x16GB DDR5
Memory Channels      → Dual Channel
Device SKU           → SM-S948W
SoC Variant          → for Galaxy
Host Motherboard     → MSI B550-A PRO
```

## Power identity

The extracted fields feed `power_identity.py`, allowing increasingly narrow learned power distributions. Conflicting controller/NAND, GPU revision/VBIOS/host, RAM topology, Apple configuration or mobile SKU/SoC facts prevent exact observations from being combined.

The specificity path is therefore able to improve from a broad family fallback toward identities such as:

```text
NVMe SSD
  → exact model
  → Phison E18 + Micron 176L TLC + 1TB

RTX 3090
  → exact board MPN
  → PCB revision + VBIOS
  → host CPU + motherboard + PSU + RAM context
```

## Seller firmware evidence

Structured marketplace listings may expose explicit seller-stated PCB revision or currently installed BIOS/UEFI. These are stored as `seller_firmware_evidence` with `source_type=seller_listing_text` and medium confidence.

Seller firmware evidence is now correlated against the selected CPU's manufacturer minimum BIOS and, when available, official revision-scoped BIOS history. The highest-confidence seller-side case requires all of the following:

```text
seller states PCB revision
+ seller states installed BIOS
+ vendor-safe BIOS comparator proves installed >= required
+ official history for that PCB revision contains the installed version
```

That can produce `ready_by_correlated_seller_installed_firmware`, but it still remains below explicit manufacturer factory/shipped-BIOS evidence. Seller claims never overwrite manufacturer CPU-support matrices, manufacturer BIOS histories, or official factory firmware statements.

A seller-stated BIOS that compares below the selected CPU minimum produces an update-required warning instead of false readiness. An unknown vendor version format remains unresolved.

## Manufacturer BIOS APIs

Deep manufacturer BIOS endpoint probing runs both generic BIOS-history normalization and revision-scoped normalization. When an official API payload explicitly associates a release with PCB/hardware revision metadata, the row retains `board_revisions`; `structured_specs.py` now persists those rows in `revision_bios_history` alongside the generic history.

Unscoped releases remain unscoped. Revision history still does not prove which BIOS a specific retail board shipped with or currently has installed; it only corroborates that a particular firmware release is valid/history-backed for a revision.

## Evidence boundary

The guiding rule is:

```text
explicit manufacturer factory evidence
    > structured manufacturer identity/history
    > verified manufacturer text
    > correlated seller listing evidence
    > uncorrelated seller listing evidence
    > inference
    > unknown
```

Unknown remains preferable to merging incompatible power measurements or claiming firmware readiness without evidence.
