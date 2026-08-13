# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware — including discrete GPUs.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, discrete GPUs, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

You do **not** need to own every product. The catalog and market-intelligence layers answer:

> **What can I buy, what does the complete usable node cost, what can it probably fit/run, what software/host infrastructure does it need, what might it cost to operate, how strong is the evidence, and is it a good deal?**

Current market snapshot: **August 10, 2026**. Prices and variants change; verify exact SKUs before purchasing.

## Complete-node cost, not sticker-price theater

A GPU/card is not compared with an integrated mini PC on board price alone.

```text
product price
    │
    ├── host
    ├── RAM
    ├── storage
    ├── PSU
    ├── PCIe / OCuLink / riser
    ├── cooling
    └── chassis / integration
    │
    ▼
complete-node acquisition
    │
    + idle/load electricity scenario
    │
    ▼
TOTAL COST OF OWNERSHIP
```

For example, a CA$500 used 24GB GPU can be a worse complete-node deal than a CA$700 integrated system when the GPU still needs several hundred dollars of host infrastructure and much higher ongoing power.

`data/market/tco-scenarios.json` contains **editable planning assumptions**, not claimed live prices or electricity tariffs. Replace them with sourced local values before a purchase decision.

```bash
llm-cluster-refresh tco --scenario mixed-3yr
llm-cluster-refresh tco --scenario always-on-3yr
llm-cluster-refresh recommendations --scenario high-electricity-3yr
llm-cluster-refresh tco-scenarios
```

Autonomous refresh generates `reports/current/daily-tco.md/json` and re-ranks the final Buy/Watch/Ignore/Experimental recommendations using complete-node acquisition + operating cost.

GPU TGP/TBP remains **board power**. When complete-node wall input is not measured, TCO uses an explicitly low-confidence planning estimate that adds host and PSU/cooling assumptions. It is never relabeled as measured tokens/joule.

## v0.5 market intelligence

```text
manufacturer pages     distributors       marketplaces
 JSON-LD offers       Mouser / DigiKey       eBay CA
       │                    │                   │
       └────────────────────┼───────────────────┘
                            ▼
                    async discovery
                            │
             SKU / seller / lifecycle
                            │
                            ▼
                       price history
                            │
                 Bank of Canada FX
                            │
                            ▼
                 Canadian landed cost
                            │
                      TCO + decision
                            │
                            ▼
                BUY / WATCH / IGNORE /
                    EXPERIMENTAL
```

Named refresh profiles live in `data/market/profiles.json`:

```bash
llm-cluster-refresh run daily-market
llm-cluster-refresh run weekly-deep-scan
llm-cluster-refresh health
llm-cluster-refresh stale --hours 72
llm-cluster-refresh alerts
llm-cluster-refresh recommendations
```

Transient HTTP/network failures use exponential backoff and jitter; rate-limited/failed sources cannot manufacture disappearance events. Source budgets, watchlists, price-drop alerts, stock returns, all-time lows, benchmark changes and decision reports remain separate evidence layers.

## Automatic hardware identity enrichment

Identity is now enriched **before** matching, price history, adaptive power learning, TCO, and recommendations. Structured source data is preferred over prose: schema.org `additionalProperty`, DigiKey parameters, distributor attributes/specifications, and eBay aspects can preserve explicit identity fields such as:

- SSD/NVMe controller, NAND type/revision, interface, and capacity;
- GPU board partner/MPN, PCB/board revision, VBIOS, and explicit host CPU/motherboard/PSU/RAM context;
- DIMM/module count, per-module capacity, channel topology, and DDR/LPDDR generation;
- mobile device SKU/model, SoC, and explicit SoC variant.

Marketplace short descriptions are also fed into the conservative text fallback. Existing structured values always win; text only fills missing explicit facts and never guesses silicon, PCB revisions, GPU bins, SSD controllers, NAND, or SoC variants.

These increasingly narrow identities feed the self-improving power model, so an exact SSD controller/NAND combination or GPU board + host configuration can form its own measured power distribution instead of contaminating a broad family average.

See `docs/AUTOMATIC_IDENTITY_ENRICHMENT.md` and `docs/HARDWARE_POWER_IDENTITY.md`.

## Firmware and first-boot readiness

Motherboard firmware evidence is evaluated separately from performance. The project preserves CPU support matrices, minimum BIOS versions, vendor-aware version ordering, BIOS Flashback/CPU-less recovery, generic BIOS history, and revision-scoped manufacturer BIOS history.

Structured marketplace listings can additionally retain seller-stated **PCB revision + currently installed BIOS/UEFI**. Seller evidence is lower authority than manufacturer evidence, but it can improve first-boot confidence after conservative correlation:

```text
seller board revision 1.2
        +
seller installed BIOS F14
        +
manufacturer revision-1.2 history contains F14
        +
selected CPU requires F12
        +
Gigabyte-safe comparison: F14 > F12
        │
        ▼
ready_by_correlated_seller_installed_firmware
```

A seller claim never overwrites an official CPU-support matrix, factory/shipped-BIOS statement, or manufacturer BIOS history. Unknown vendor version formats remain unresolved.

See `docs/FIRMWARE_BOOT_READINESS.md` and `docs/BIOS_VERSIONING.md`.

## Evidence, not pretend precision

Performance provenance remains explicit:

```text
measured_local
community_measured
vendor_measured
derived_estimate
spec_based_estimate
unknown
```

The project does **not** manufacture tokens/sec from TOPS, TFLOPS, memory bandwidth, core count or TDP/TGP/TBP. Model-fit estimates are transparent capacity screens only.

## GPU rules

Discrete GPUs are first-class `gpu_accelerator` products. Fixed VRAM counts as model-capacity memory; board power does not count as complete-system power.

The initial catalog covers RTX 5060 Ti 16GB, RTX 3090 24GB, RX 9070/9070 XT 16GB, Arc B580 12GB and Arc A770 16GB, with autonomous GPU market queries and a `gpu-value` watchlist.

See `docs/GPUS.md` and `docs/TOTAL_COST_OF_OWNERSHIP.md`.

## Memory semantics

- `memory_capacity_gb` — actually included/fixed RAM or VRAM;
- `max_memory_gb` — verified board/product maximum;
- `cpu_max_memory_gb` — processor-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

A barebone does not magically include the CPU's theoretical maximum RAM.

## Browse the catalog

```bash
python -m pip install -e .
llm-cluster rank
llm-cluster list --llm-only --max-price 250
llm-cluster list --llm-only --min-memory 32 --sort price
llm-cluster show special-amd-bc250-16g
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## Repository map

- `data/catalog/` — curated hardware records, including `gpus.json`.
- `data/market/sources.json` — source configuration without secrets.
- `data/market/profiles.json` — autonomous polling profiles and TCO scenario selection.
- `data/market/watchlists.json` — alert/watch targets including GPU value.
- `data/market/tco-scenarios.json` — editable infrastructure, power and electricity planning assumptions.
- `data/market/price-history.json` — append-only market observations.
- `data/evidence/performance.json` — sourced benchmark evidence.
- `reports/current/` — current buying, change, decision and TCO reports.
- `docs/AUTOMATIC_IDENTITY_ENRICHMENT.md` — listing/manufacturer identity extraction rules.
- `docs/HARDWARE_POWER_IDENTITY.md` — narrow identity and learned power-distribution methodology.
- `docs/FIRMWARE_BOOT_READINESS.md` — CPU/BIOS, Flashback and boot-readiness evidence.
- `docs/BIOS_VERSIONING.md` — conservative vendor BIOS ordering.
- `docs/DECISION_QUALITY.md` — recommendation methodology.
- `docs/TOTAL_COST_OF_OWNERSHIP.md` — complete-node cost methodology.
- `docs/GPUS.md` — GPU sourcing and evidence rules.
- `benchmarks/` — optional local measurement tooling.
- `PARTS.md` — deterministic human-readable catalog view.

## Design rule

The catalog is the durable product identity layer. Listings, component prices, exchange rates, benchmark results and TCO assumptions are evidence with explicit provenance. A partial component price must never masquerade as the cost of a complete usable node.
