# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

You do **not** need to own every product. The job of the catalog is to answer:

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

Current market snapshot: **August 10, 2026**. Prices and variants change; verify exact SKUs before purchasing.

## The project in one picture

```text
                     PRODUCT DISCOVERY
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
    mini PCs            dev/SBCs          accelerators
 Ryzen / Intel        RK3588 / Jetson   NPU/TPU/ASIC/FPGA
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                     PRODUCT CATALOG
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       price/URL       model-fit screen   evidence
       lifecycle       RAM/software       provenance
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    BUYING SHORTLIST
                           │
             optional real benchmarks
             when hardware/data exists
```

## Evidence, not pretend precision

A product can be valuable even when no local benchmark exists. Performance evidence is labelled by provenance:

```text
measured_local       highest direct confidence when reproducible
community_measured   useful third-party evidence
vendor_measured      useful, but preserve workload details
derived_estimate     math based on measured evidence
spec_based_estimate  weak planning clue only
unknown              completely acceptable
```

The project **will not manufacture tokens/sec** from TOPS, TFLOPS, memory bandwidth, core count or TDP.

## What can be estimated safely?

Model-weight capacity can be screened transparently:

```text
parameters × nominal bits/weight
              │
              ▼
      approximate weight size
              +
   explicit planning headroom
              │
              ▼
     compare with catalog RAM
```

This answers **"is this worth investigating for a model this size?"** It does *not* predict speed and cannot know exact KV-cache/runtime overhead without a specific model/backend.

Example:

```bash
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## Memory semantics matter

A barebone with a CPU that theoretically supports 256GB does **not** contain 256GB. v0.4.1 separates:

- `memory_capacity_gb` — RAM actually included/fixed in that referenced configuration;
- `max_memory_gb` — verified maximum for the board/product, when known;
- `cpu_max_memory_gb` — processor-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

That prevents shopping rankings and model-fit screens from being distorted by CPU datasheets.

## Browse the catalog

```bash
python -m pip install -e .

# Buying/research shortlist — not a performance benchmark
llm-cluster rank

# Browse likely LLM-capable hardware under $250
llm-cluster list --llm-only --max-price 250

# Find 32GB+ candidates
llm-cluster list --llm-only --min-memory 32 --sort price

# Inspect one record and its evidence status
llm-cluster show special-amd-bc250-16g

# Conservative capacity screen for a 14B 4-bit model
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## Hardware families

The catalog intentionally spans different kinds of useful hardware:

| Class | Examples | Why track it? |
|---|---|---|
| low-power x86 | Ryzen 7735U/8845HS, N100 | common Linux ecosystem, replaceable RAM on many models |
| high-memory mobile boards | 8745HS/HX370/7945HX | dense CPU/APU compute with laptop-class efficiency |
| unusual APU | AMD BC-250 | cheap unified GDDR6 and interesting Vulkan potential |
| ARM/SBC | RK3588, Jetson Orin | very low power and compact always-on nodes |
| GenAI NPU/TPU | Hailo-10H, SOPHGO | purpose-built inference paths at low power |
| AI ASIC | Tenstorrent | open/interesting accelerator architecture and fast local memory |
| FPGA/adaptive | Kria, Versal, Alveo | custom low-precision research potential |
| specialist | Coral, MemryX | vision/audio offload can keep larger nodes asleep |
| decommissioned | Alveo/NCS2/etc. | liquidation pricing can create strange bargains |

See **[PARTS.md](PARTS.md)** for the generated current catalog and direct URLs.

## Catalog score vs performance

`llm-cluster rank` is deliberately shopping-oriented. It considers things like price, memory evidence, power hints, software maturity, lifecycle and risk.

```text
CATALOG SCORE                   PERFORMANCE EVIDENCE
─────────────                   ────────────────────
price                           measured tokens/sec
RAM included/potential          vendor/community result
power hint                      complete-node watts
software maturity               tokens/joule
risk / availability             model-specific throughput

            kept as separate dimensions
```

A high catalog score means **"worth investigating"**, not "fastest LLM hardware."

## Optional benchmark subsystem

The v0.4 `llm-cluster-bench` harness remains in the repository. It is useful for your own ThinkPad L14 or contributed third-party hardware, but it is no longer the center of the project.

```text
YOUR / CONTRIBUTED HARDWARE
           │
           ▼
   optional benchmark harness
           │
           ▼
 reproducible evidence record
           │
           ▼
       product catalog
```

See [docs/BENCHMARK_HARNESS.md](docs/BENCHMARK_HARNESS.md).

## Repository layout

```text
LowPowerLLMCluster/
├── data/parts.json             catalog manifest
├── data/catalog/               product records by family
├── PARTS.md                    generated human-readable catalog
├── specs/HARDWARE_CATALOG.md   product data contract
├── specs/EVIDENCE.md           provenance + safe estimation rules
├── docs/PROJECT_CHARTER.md     catalog-first mission
├── docs/GUARDRAILS.md          anti-drift / anti-fake-performance rules
├── src/lowpower_llm_cluster/   browser, scoring, fit planner
├── benchmarks/                 optional benchmark profiles
└── results/                    optional reproducible measurements
```

## Next priorities

The next releases should concentrate on the catalog itself:

1. automated product discovery and price refresh;
2. historical pricing and listing-disappearance tracking;
3. CAD/landed-cost estimates;
4. more exact memory/configuration metadata;
5. sourced vendor/community benchmark ingestion with confidence labels;
6. filters such as best under $100/$200/$500, high-memory bargains, low-power nodes and weird-hardware deals;
7. use the ThinkPad L14 as an optional local reference/calibration node—not as a requirement to own everything else.

## Data quality rule

**Measured ≠ published ≠ community-reported ≠ derived ≠ speculative.**

The distinction is a feature of the project, not an inconvenience.
