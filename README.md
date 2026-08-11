# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

You do **not** need to own every product. The job of the catalog is to answer:

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

Current market snapshot: **August 10, 2026**. Prices and variants change; verify exact SKUs before purchasing.

## v0.5 market intelligence

v0.5 turns the static catalog into a time-aware research pipeline without allowing volatile listings to overwrite curated hardware facts:

```text
product sources
      │
      ▼
async discovery adapters
      │
      ▼
normalized listings ──────► exact SKU/config confidence
      │                              │
      ▼                              ▼
price observations              catalog match
      │                              │
      └──────────────┬───────────────┘
                     ▼
                price history
                     │
        sourced FX / shipping / tax
                     │
                     ▼
            Canadian landed cost

vendor/community measurements
              │
              ▼
      performance evidence
 model + runtime + workload + source
```

The source-adapter interface is async-first. Network adapters must use non-blocking clients; blocking SDK or filesystem calls are isolated from the event loop.

The initial JSON-feed adapter is a deterministic import/fixture boundary for source-specific collectors:

```bash
llm-cluster-market discover --feed listings.json --query "Ryzen 8845HS"
llm-cluster-market history special-amd-bc250-16g
llm-cluster-market landed listing.json --tax-rate 0.12
llm-cluster-market ingest-performance performance-records.json
```

`data/market/fx-cad.json` deliberately ships without a made-up USD/CAD rate. Add a sourced rate snapshot before converting non-CAD listings. Landed cost keeps item, shipping, duty, brokerage and tax separate because Canadian customs treatment depends on the actual shipment.

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

The project **will not manufacture tokens/sec** from TOPS, TFLOPS, memory bandwidth, core count or TDP. v0.5 performance imports additionally require the source URL, exact model/variant where known, runtime/backend, workload/phase, metric and unit.

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

A barebone with a CPU that theoretically supports 256GB does **not** contain 256GB. The catalog separates:

- `memory_capacity_gb` — RAM actually included/fixed in that referenced configuration;
- `max_memory_gb` — verified maximum for the board/product, when known;
- `cpu_max_memory_gb` — processor-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

v0.5 applies the same rule to listing matching: CPU-theoretical RAM does not increase configuration confidence.

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
| GenAI accelerators | Hailo, SOPHGO, Tenstorrent | alternative transformer runtimes worth tracking |
| FPGA/adaptive SoC | Kria, Versal, Alveo | research/custom datapaths and unusual memory systems |
| specialist accelerators | Coral, MemryX, NCS2 | route vision/audio/classification away from LLM nodes |

## Repository map

- `data/catalog/` — curated hardware catalog fragments.
- `data/market/` — time-varying listing/price/FX evidence.
- `data/evidence/` — sourced performance evidence.
- `specs/HARDWARE_CATALOG.md` — catalog contract.
- `specs/EVIDENCE.md` — evidence and estimation guardrails.
- `specs/MARKET_INTELLIGENCE.md` — discovery, pricing, Canadian cost and performance-ingestion contract.
- `benchmarks/` — optional local measurement tooling.
- `PARTS.md` — deterministic human-readable catalog view.

## Design rule

The catalog is the durable product identity layer. Listings, prices, exchange rates and benchmarks are evidence with timestamps and provenance. Evidence may strengthen or weaken a buying recommendation, but it must not silently rewrite a product into a different SKU/configuration.
