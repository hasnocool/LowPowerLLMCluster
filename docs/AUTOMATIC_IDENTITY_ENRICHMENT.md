# Automatic Identity Enrichment

This layer extracts explicit hardware identity facts as early as possible, before price matching, learned power aggregation, TCO or recommendation scoring.

## Source normalization

Every normalized `Listing` receives a conservative text pass that may fill missing explicit fields for:

- SSD/NVMe controller, NAND type, interface and capacity context;
- GPU board partner, PCB/board revision and VBIOS;
- RAM module count, per-module capacity, channel count and memory type;
- mobile device SKU, model, SoC and SoC variant;
- accelerator host CPU, motherboard, PSU and RAM context.

Structured source fields always win. The text parser only fills missing values and never invents silicon from a family name.

## Power identity

The extracted fields feed `power_identity.py`, allowing increasingly narrow learned power distributions. Conflicting controller/NAND, GPU revision/VBIOS/host, RAM topology, Apple configuration or mobile SKU/SoC facts prevent exact observations from being combined.

## Seller firmware evidence

Structured marketplace titles may expose explicit seller-stated PCB revision or currently installed BIOS/UEFI. These are stored as `seller_firmware_evidence` with `source_type=seller_listing_text` and medium confidence.

Seller firmware text can help first-boot analysis but must not override manufacturer CPU-support matrices, manufacturer BIOS histories or official factory/shipped BIOS statements.

## Manufacturer BIOS APIs

Deep manufacturer BIOS endpoint probing now runs both generic BIOS-history normalization and revision-scoped normalization. When an official API payload explicitly associates a release with PCB/hardware revision metadata, the row retains `board_revisions`. Unscoped releases remain unscoped.

Revision history still does not prove which BIOS a specific retail board shipped with or currently has installed. That requires explicit factory/manufacturer evidence or separately identified seller evidence.

## Evidence boundary

The guiding rule is:

```text
structured exact fact > verified manufacturer text > seller-stated fact > inference > unknown
```

Unknown remains preferable to merging incompatible power measurements or claiming firmware readiness without evidence.
