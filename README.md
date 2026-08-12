# LowPowerLLMCluster

**A catalog-first research, buying and evidence-backed workload placement planner for cheap, efficient and unusual local-AI hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, GPUs and interesting decommissioned accelerators.

You do **not** need to own every product. The project can answer two different questions without mixing them:

> **What hardware is worth investigating or buying?**

and, when real performance evidence exists:

> **Which available device is the best place to run this workload under my model, power, energy, budget and off-grid constraints?**

Current market snapshot: **August 10, 2026**. Prices and variants change; verify exact SKUs before purchasing.

## The project in one picture

```text
                     PRODUCT DISCOVERY
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
    mini PCs            dev/SBCs          accelerators
 Ryzen / Intel        RK3588 / Jetson   GPU/NPU/TPU/FPGA
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
          └────────────┬───┴────────────────┘
                       ▼
                BUYING SHORTLIST
                       │
          sourced / measured benchmarks
                       │
                       ▼
             NORMALIZED OPTIMIZER
                       │
       ┌───────────────┼─────────────────┐
       ▼               ▼                 ▼
   workload fit     energy/cost       off-grid fit
   model/context    task Wh/time      battery/solar
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

A barebone with a CPU that theoretically supports 256GB does **not** contain 256GB. The catalog separates:

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

## v0.5 heterogeneous AI optimizer

`llm-cluster-optimize` compares unlike hardware on a common evidence-aware scale while keeping each tradeoff visible. It supports Ryzen APUs, RTX-style GPUs, Apple Silicon, Intel/AMD NPUs, Coral-style specialist TPUs, BC-250, Raspberry Pi accelerators and old datacenter hardware as long as the input record describes what is actually known.

The core normalized dimensions are:

```text
LLM speed
model capacity
AI compute (theoretical, kept separate)
power efficiency
cost efficiency
off-grid suitability
```

Operational dimensions are also reported:

```text
software support
deployability
reliability from soak evidence
sustained-performance ratio
thermal headroom
energy proportionality
```

Workload profiles currently include `interactive_chat`, `coding_agent`, `long_context`, `always_on_agent`, `off_grid_ai` and `vision`.

Try the included example:

```bash
llm-cluster-optimize data/scoring.example.json \
  --workload off_grid_ai \
  --model-params-b 14 \
  --bits 4 \
  --prompt-tokens 2000 \
  --output-tokens 1000 \
  --battery-wh 500 \
  --solar-w 250
```

Apply hard constraints:

```bash
llm-cluster-optimize data/scoring.example.json \
  --workload coding_agent \
  --model-params-b 14 \
  --min-decode 15 \
  --max-power 80 \
  --budget 300
```

Show only candidates on the measured time/energy Pareto frontier:

```bash
llm-cluster-optimize data/scoring.example.json \
  --workload off_grid_ai \
  --output-tokens 2000 \
  --pareto
```

Machine-readable output is available with `--json`.

### Why this is different from TOPS/TFLOPS ranking

TOPS/TFLOPS are retained as **theoretical compute evidence**. They can contribute to the AI-compute dimension but are never converted into fake LLM throughput. Practical LLM speed requires measured/sourced decode/prefill evidence.

When measured complete-node power and throughput exist, the optimizer may calculate arithmetic derivatives:

```text
tokens/joule
joules/token
tokens/kWh
task seconds
Wh/task
battery runtime / tokens per battery
solar recovery hours
```

Board-only accelerator power is not accepted as canonical whole-system power for tokens/joule.

### Hard compatibility gates

Known failures are rejected before ranking, including insufficient verified memory/context, runtime or precision incompatibility, throughput below a requested floor, excessive complete-system watts, excessive task Wh and purchase cost above budget. Unknown evidence remains unknown instead of being silently invented.

### Cluster and scheduling primitives

The scoring library also includes helpers for aggregate usable memory, combined power, ideal independent throughput and **measured** distributed scaling efficiency. This is the base layer for future dynamic workload placement across multiple local nodes and specialist accelerators.

See **[specs/SCORING.md](specs/SCORING.md)** for the scoring contract and **[specs/normalized-device.schema.json](specs/normalized-device.schema.json)** for optimizer input fields.

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

## Catalog score vs measured optimization

`llm-cluster rank` is deliberately shopping-oriented. It considers price, memory evidence, power hints, software maturity, lifecycle and risk.

```text
CATALOG SCORE                   OPTIMIZER / PERFORMANCE EVIDENCE
─────────────                   ────────────────────────────────
price                           measured decode/prefill
RAM included/potential          measured complete-node watts
power hint                      tokens/joule and task Wh
software maturity               model/context fit
risk / availability             workload profile + hard gates

            kept as separate systems
```

A high catalog score means **"worth investigating"**, not "fastest LLM hardware."

## Optional benchmark subsystem

The `llm-cluster-bench` harness remains the source of reproducible local measurements. Benchmark-schema-v2 output can be passed directly to `llm-cluster-optimize`; the bridge imports measured LLM or vision throughput and only accepts `complete_node_input` power for canonical system-efficiency calculations.

```text
YOUR / CONTRIBUTED HARDWARE
           │
           ▼
   optional benchmark harness
           │
           ▼
 reproducible evidence record
           │
      ┌────┴────┐
      ▼         ▼
   catalog    optimizer
```

See [docs/BENCHMARK_HARNESS.md](docs/BENCHMARK_HARNESS.md).

## Repository layout

```text
LowPowerLLMCluster/
├── data/parts.json                       catalog manifest
├── data/catalog/                         product records by family
├── data/scoring.example.json             optimizer example input
├── PARTS.md                              generated human-readable catalog
├── specs/HARDWARE_CATALOG.md             product data contract
├── specs/EVIDENCE.md                     provenance + safe estimation rules
├── specs/SCORING.md                      catalog + normalized optimizer scoring
├── specs/normalized-device.schema.json   optimizer device contract
├── docs/PROJECT_CHARTER.md               catalog-first mission
├── docs/GUARDRAILS.md                    anti-drift / anti-fake-performance rules
├── src/lowpower_llm_cluster/             catalog, benchmark and optimizer code
├── benchmarks/                           optional benchmark profiles
└── results/                              optional reproducible measurements
```

## Next priorities

1. ingest real vendor/community/local benchmark evidence into normalized device records;
2. populate comparable Ryzen APU, RTX GPU, Apple Silicon, NPU, Coral/vision, BC-250 and SBC cohorts;
3. add live battery/solar telemetry and dynamic local-node placement;
4. add interconnect-aware multi-node placement and measured cluster scaling;
5. automate product discovery, price refresh and historical pricing;
6. add CAD/landed-cost estimates and exact-SKU configuration confidence;
7. add dashboard views for score dimensions, Pareto fronts, battery runtime and solar recovery.

## Data quality rule

**Measured ≠ published ≠ community-reported ≠ derived ≠ speculative.**

The distinction is a feature of the project, not an inconvenience.
