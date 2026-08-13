# Real Power Evidence and Factory Firmware Provenance

This layer grows accuracy by adding **more trustworthy evidence** without weakening the project's existing evidence boundaries.

## Exact power evidence feed

`data/evidence/power-measurements.json` is a curated feed for measured power observations that are not already represented by benchmark records.

Every record must provide:

- an HTTPS source URL;
- a measured source class (`measured_local`, `vendor_measured`, or `community_measured`);
- an explicit power boundary such as complete-node wall input or accelerator-board power;
- enough hardware identity to prevent measurements from being merged with incompatible configurations;
- idle and/or load watts.

Internal-rail measurements may be retained for research but are not eligible to train complete-device wall-power estimates.

The initial real observations include:

- a 16.2-inch 2021 MacBook Pro with M1 Max 32-core GPU, 64GB unified memory and 2TB SSD measured at complete-node wall input by Notebookcheck;
- an MSI GeForce RTX 3090 Gaming X Trio board-power measurement from TechPowerUp, retained strictly as accelerator-board power rather than complete-node input.

`refresh_power_evidence()` combines this feed with catalog power facts, exact benchmark measurements, and manufacturer-spec power fields. Narrow hardware identities win over family/category distributions, while direct measurements still outrank learned estimates.

## Vendor structured-parameter aliases

`data/identity/vendor-parameter-mappings.json` maps manufacturer/distributor parameter **labels** to normalized identity fields.

Examples include controller IC → SSD controller, NAND Flash Type → NAND type, VBIOS → VBIOS version, PCB Revision → GPU/board revision, and Memory Kit Configuration → RAM topology.

The registry is value-neutral: it only maps a label. The actual hardware value must be explicitly supplied by the source. Alias rules must never invent controller silicon, NAND type, PCB revision, firmware version, SoC variant, or host configuration.

## Factory-firmware provenance

`data/firmware/factory-firmware-rules.json` and `factory_firmware.py` support manufacturer-published relationships between a physical board identity and its factory BIOS.

Supported evidence rule types are:

- exact serial mappings;
- vendor-published serial decoding patterns;
- manufacture-batch mappings;
- board-revision mappings;
- documented physical factory-BIOS label/sticker methods.

There is intentionally **no generic serial-number decoder**. A serial or batch observed in a seller listing remains informational until an explicit manufacturer source documents how it maps to a board revision or factory BIOS.

The first documented inspection method is ASRock's official guidance that the sticker on the BIOS chip contains the default BIOS version. This lets a seller/photo-derived sticker value become manufacturer-authorized factory-BIOS evidence because the interpretation method itself is published by ASRock; it is not a guessed serial mapping.

## Boot-readiness authority order

For a CPU requiring a minimum BIOS, readiness evidence is ordered roughly as:

```text
explicit manufacturer shipped BIOS
        ↓
verified manufacturer factory BIOS mapping/label
        ↓
seller installed BIOS + official revision history
        ↓
seller installed BIOS with vendor-safe version comparison
        ↓
CPU-less Flashback/recovery evidence
        ↓
unknown / update-risk fallback
```

A verified factory BIOS that safely meets the selected CPU minimum can reach `ready_with_verified_factory_firmware`. If the verified factory BIOS is below the minimum, the build remains compatible only with an explicit firmware-update requirement.

## Extension rule

When a new vendor is encountered, add a factory mapping only if the relationship is documented by the manufacturer. Reverse-engineered community serial patterns may be useful research leads, but they must not be promoted to manufacturer-authoritative first-boot evidence without vendor documentation.
