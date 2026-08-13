# Evidence Harvesting

The v0.5 market-intelligence branch is now primarily limited by **evidence volume**, not by the matching architecture. This document defines how to grow measured-power and factory-firmware evidence without weakening provenance.

## Power evidence admission order

Prefer evidence in this order:

1. exact complete-node/device wall-input measurements;
2. exact component/board measurements with an explicit non-wall boundary;
3. exact manufacturer power fields with a documented scope;
4. compatible benchmark-derived watts only when throughput and tokens/joule share the exact same signature;
5. learned family/category distributions;
6. static fallback estimates.

Every measured record belongs in `data/evidence/power-measurements.json` and must include:

- an HTTPS source URL;
- `source_type` identifying the measurement authority;
- an explicit `power_scope`;
- enough hardware identity to prevent incompatible configurations from being pooled;
- at least one measured idle/load value;
- a note describing the workload and any measurement caveat.

Do **not** convert charger wattage, battery capacity, TDP/TGP/TBP, internal telemetry rails, or accelerator-board measurements into complete-node wall input.

## Current harvested batch

The first curated batch now spans multiple device classes instead of concentrating on one family.

| Device/configuration | Measurement boundary | Idle W | Load W | Max W | Source class |
| --- | --- | ---: | ---: | ---: | --- |
| MacBook Pro 16 (2021), M1 Max 32-core GPU, 64GB, 2TB | complete-node wall input | 16.4 | 94.0 | 135.0 | community measured |
| Mac mini M4, 10-core GPU, 16GB, 256GB | complete-node AC input | 2.65 | 31.5 | 62.5 | community measured |
| Mac mini M4 Pro, 16-core GPU, 64GB, 2TB | complete-node AC input | 2.59 | 31.4 | 70.1 | community measured |
| MacBook Pro 16 (2024), M4 Max 40-core GPU, 48GB, 1TB | complete-node wall input | 15.5 | 125.0 | 143.7 | community measured |
| Minisforum UM780 XTX, Ryzen 7 7840HS, 32GB, 1TB | complete-node AC input | 10.5 | 67.2 | 97.2 | community measured |
| Pixel 10 Pro XL, Tensor G5, 16GB, 256GB | measured device input | 1.34 | 4.38 | 16.3 | community measured |
| Galaxy S26 Ultra, Snapdragon 8 Elite Gen 5 for Galaxy, 12GB, 256GB | measured device input | 1.18 | 14.91 | 16.58 | community measured |
| MSI GeForce RTX 3090 Gaming X Trio | accelerator-board power only | — | 350.0 | — | community measured |

These values are **general device/load measurements**, not claims about LLM-specific inference wattage unless the source workload explicitly is an LLM run. They improve total-ownership and fallback estimates, but LLM-specific tokens/joule still requires a compatible benchmark workload.

## Identity requirements by hardware class

### Apple systems

Record, when available:

- exact SoC and CPU/GPU bin;
- unified-memory capacity;
- storage capacity;
- screen size for laptops;
- model identifier, A-number, or part/order number when the source exposes it.

Do not transfer one MacBook/Mac-mini power sample to another enclosure merely because both use the same SoC.

### GPUs

Prefer:

- board partner and exact model/MPN;
- PCB revision and VBIOS when known;
- whether power is card-only or whole-system;
- for whole-system measurements, host CPU, motherboard, RAM, PSU and relevant power-limit/undervolt state.

Board-only measurements may help estimate accelerator contribution but must never be relabeled as complete-node wall input.

### SSDs

Prefer exact:

- model/capacity;
- controller;
- NAND generation/type;
- DRAM presence/configuration;
- PCIe generation/interface;
- idle, workload-average and maximum values from a direct SSD power instrument when available.

SSD reviews whose numeric results only exist in inaccessible chart images should not be transcribed from visual guesses. Wait for text/structured figures or another auditable source.

### RAM

Capture:

- memory generation/type;
- module count;
- capacity per module;
- rank/channel topology where known;
- platform voltage/profile if explicitly measured.

### Phones/tablets

Capture:

- exact device model/SKU;
- SoC and SoC variant;
- RAM/storage configuration;
- display state/brightness and workload when the measurement methodology supplies it.

Charger rating is not device consumption.

### SBCs, mini PCs and unusual accelerators

Prefer whole-device input measurements. Manufacturer power modes such as Jetson 7W/15W/25W are valid power-budget/spec evidence, but they are not automatically equivalent to a measured wall-input value.

## Factory-firmware harvesting

`data/firmware/factory-firmware-rules.json` may only grow from explicit vendor-published mappings or inspection methods.

Admissible examples include:

- exact serial to factory BIOS;
- documented serial-pattern decoding;
- manufacture-batch to factory BIOS;
- PCB revision to factory BIOS;
- a manufacturer-documented physical label/sticker that explicitly represents default/factory BIOS.

Do not reverse-engineer serial conventions and present them as vendor authority. A manufacture date plus a BIOS release date does not prove which BIOS shipped on a specific board.

The initial real factory-firmware rule remains ASRock's documented BIOS-chip sticker method. Other vendors stay unresolved until an equally explicit public mapping is found.

## Highest-value evidence gaps

1. exact LLM-workload complete-node power for Apple M1/M2/M3/M4/M5 configurations;
2. GPU **board + exact host** wall-input measurements under llama.cpp/vLLM/MLC workloads;
3. SSD numeric idle/average/max measurements carrying controller + NAND identity;
4. RAM-topology incremental-power measurements;
5. more phones/tablets with exact device/SOC/RAM/storage identity;
6. RK3588, Jetson, BC-250, FPGA/ASIC/NPU and other unusual-node complete-input measurements;
7. vendor-published serial/batch/revision to factory-BIOS mappings.

The harvesting rule is simple: **more evidence is useful only when its hardware identity and measurement boundary remain explicit.**
