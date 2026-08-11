# LowPowerLLMCluster

**Build a cheap, power-efficient local LLM cluster from mini PCs, mobile-CPU boards, SBCs, development kits, embedded systems and unusual compute hardware.**

The basic idea is simple: instead of buying one giant workstation, combine heterogeneous low-power nodes and give each one the job it can do efficiently. A Ryzen mini PC, RK3588 SBC, Jetson edge board and oddball BC-250 do not need to be equally good at everything to be useful in the same cluster.

> Current hardware/pricing snapshot: **August 10, 2026**. Alibaba prices change and listings often bundle multiple variants, so confirm the exact SKU before ordering.

## The idea in one picture

```text
                              USER / CODING AGENT
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │     SMART ROUTER      │
                          │                       │
                          │ Which model?          │
                          │ Which node is awake?  │
                          │ Which is cheapest?    │
                          │ Which has enough RAM? │
                          └───────────┬───────────┘
                                      │
                               2.5GbE network
                                      │
                ┌─────────────────────┼─────────────────────┐
                │                     │                     │
                ▼                     ▼                     ▼
        ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
        │ EFFICIENT     │     │ MAIN WORKER   │     │ BIG / FAST    │
        │ WORKER        │     │               │     │ WORKER        │
        │ Ryzen 7735U   │     │ Ryzen 8845HS  │     │ 8745HS/HX370  │
        │ 32-64GB RAM   │     │ 64GB RAM      │     │ 64-96GB+      │
        │ ~15-30W CPU   │     │ HS-class CPU  │     │ expansion I/O │
        └───────────────┘     └───────────────┘     └───────────────┘
                │                     │                     │
             small LLM              coder               heavy LLM
             utility AI            general             RPC fallback
```

The router sends a complete request to the best node. That normally works better than forcing every token to travel between several computers over Ethernet.


## The project is intentionally hardware-agnostic

Laptop-class Ryzen remains a strong baseline, but v0.3 now treats **NPUs, TPUs, AI ASICs, FPGAs, adaptive SoCs and decommissioned accelerators as first-class research families**:

```text
                              HARDWARE DISCOVERY FUNNEL

 mini PCs / boards      SBCs / dev kits       GenAI accelerators       FPGA / EOL
        │                    │                       │                     │
        ▼                    ▼                       ▼                     ▼
 Ryzen 7735U/8845HS      RK3588 / Jetson        Hailo-10H NPU        AMD Kria / Versal
 mobile CPU boards       32GB ARM nodes         SOPHGO BM1688        Alveo U50 / V70
 AMD BC-250              edge systems           Tenstorrent ASIC     old Movidius VPUs
        │                    │                       │                     │
        └────────────────────┴──────────────┬────────┴─────────────────────┘
                                           ▼
                                 WORKLOAD-AWARE TESTING
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
                tokens/sec              wall watts          specialist offload
                    │                      │                      │
                    └──────────────────────┼──────────────────────┘
                                           ▼
                              tokens/joule + tokens/$ + fit
```

The rule is **measure first, specialize second**. Weird hardware is welcome, but an experimental driver hack never becomes a normal recommendation just because one benchmark is fast. See [Project Charter](docs/PROJECT_CHARTER.md) and [Guardrails](docs/GUARDRAILS.md).

### Interesting new candidate classes

| Class | Example | Why it is interesting | Main limitation |
|---|---|---|---|
| experimental specialty APU | AMD BC-250 | 16GB unified GDDR6 and very high memory bandwidth for its used price | unusual firmware/drivers, fixed 16GB, secondary market |
| edge-AI dev kit | Jetson Orin Nano Super | mature CUDA/TensorRT stack, 7-25W, 102GB/s memory bandwidth | only 8GB RAM |
| 32GB ARM SBC | Orange Pi 5 Plus | dense 32GB low-power node with 2.5GbE/NVMe | software/backend maturity varies |
| Mini-ITX ARM | Radxa ROCK 5 ITX+ | standard physical form factor and 32GB option | availability and RK3588 software ecosystem |
| high-core mobile CPU board | MINISFORUM BD795M | 16C/32T laptop silicon on standard mATX with PCIe | much higher power than tiny nodes |
| modular laptop mainboard | Framework Ryzen AI | documented standalone board and maintainable ecosystem | expensive versus direct-China barebones |
| GenAI NPU | Hailo-10H / AI HAT+ 2 | 8GB dedicated RAM, explicit LLM/VLM support and very low accelerator power | small-model memory ceiling; host power still counts |
| edge TPU / AI SoC | SOPHGO BM1688/BM1684X | maintained LLM-TPU stack with Qwen/Llama/DeepSeek support | smaller ecosystem and model conversion workflow |
| open AI ASIC | Tenstorrent Wormhole | real text-generation stack, GDDR6 and high-speed multi-card links | 160W board power; reference rather than low-power worker |
| adaptive FPGA SoC | AMD Kria / Versal | lets us test custom INT4/ternary/BitNet transformer datapaths | engineering effort; stock TOPS are not LLM benchmarks |
| decommissioned accelerator | Alveo U50/V70, old VPUs | secondary-market hardware can become attractive after enterprise liquidation | frozen/limited software and uncertain used pricing |

## Current best leads

| Role | Current lead | Snapshot price | Why it matters |
|---|---|---:|---|
| cheapest efficiency worker | Ryzen 7 7735U DDR5 mini PC/barebone | **$165** | 8C/16T with a 15-30W CPU envelope |
| strongest bargain lead | Ryzen 7 8845HS + 32GB + 1TB | **$206-220** | Zen 4 + DDR5 + Radeon 780M at an unusually low advertised price |
| most expandable | Topton FU05 Ryzen 7 8745HS | **$310-375** | dual 2.5GbE, 2x DDR5, 2x NVMe and OCuLink |
| premium performance/watt | Ryzen AI 9 HX 370 barebone | **$720** | 12C/24T, 15-54W configurable CPU envelope and Radeon 890M |
| cheap cluster switch | EDUP 8-port 2.5GbE | **$19.90-30** | enough ports for a small worker cluster |
| low-power GenAI accelerator | Raspberry Pi AI HAT+ 2 / Hailo-10H 8GB | **$200** | 40 TOPS INT4, dedicated memory, explicit LLM/VLM support |
| low-cost TPU SoM | Firefly BM1688 8GB | **$339** | official SOPHGO LLM-TPU path for Qwen/Llama/DeepSeek-class models |
| FPGA research kit | AMD Kria KV260 | **$249 MSRP** | affordable programmable transformer/low-precision research platform |
| open AI-ASIC reference | Tenstorrent Wormhole n150s | **$999** | 12GB GDDR6, 288GB/s and fast accelerator interconnect; high-power comparison node |

See **[PARTS.md](PARTS.md)** for URLs, MOQ, seller information, verification status and the reasoning behind every listing.


## Why specialist accelerators belong in the cluster

The project does **not** assume every accelerator should run an LLM. A small fixed-function device can still reduce total power if it handles vision, detection, audio or embeddings while the larger LLM node sleeps. Devices only receive `llm_candidate=true` when there is a real model/runtime path—not because their marketing page has a large TOPS number.

```text
                    incoming request
                           │
                           ▼
                   classify workload
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       vision           small LLM        large LLM
          │                │                │
          ▼                ▼                ▼
   Coral / MemryX     Hailo / SOPHGO    Ryzen / BC-250
      ~few watts       dedicated AI       large memory
```

See [docs/ACCELERATORS.md](docs/ACCELERATORS.md) for the accelerator taxonomy, lifecycle rules and benchmark requirements.

## Why laptop-class CPUs?

Mobile Ryzen processors are interesting because they already solve several problems a DIY cluster has:

- lots of CPU cores at relatively modest package power;
- integrated graphics that llama.cpp can potentially use through supported backends;
- DDR5/LPDDR5 memory bandwidth;
- small cooling requirements;
- compact boards;
- common 19-20V-class external power-brick designs in mini PCs;
- inexpensive used/new ecosystem.

A replacement laptop motherboard is often awkward because it expects proprietary batteries, keyboards, display cables and embedded-controller behavior. A mobile-CPU mini-PC or embedded board gives you laptop silicon without needing the rest of the laptop.

## The most important LLM constraint: memory

For local LLM generation, raw CPU GHz is not the whole story. The model weights must be read repeatedly from memory, so **RAM capacity and bandwidth matter a lot**.

```text
                       WHAT TO BUY FIRST

                 ┌────────────────────────┐
                 │ Enough RAM for model?  │
                 └───────────┬────────────┘
                             │ yes
                             ▼
                 ┌────────────────────────┐
                 │ Good memory bandwidth? │
                 └───────────┬────────────┘
                             │ yes
                             ▼
                 ┌────────────────────────┐
                 │ Efficient CPU / iGPU?  │
                 └───────────┬────────────┘
                             │ yes
                             ▼
                 ┌────────────────────────┐
                 │ Network + expansion?   │
                 └────────────────────────┘
```

That is why a 64GB node can be more useful than a faster processor stuck at 16GB or 32GB.

## Why not make 2.5GbE behave like one huge RAM pool?

Because it cannot.

```text
DDR5 memory       ================================> tens of GB/s
2.5Gb Ethernet    => about 0.3125 GB/s theoretical line rate
```

Ethernet is excellent for sending **requests** to another node. It is much less attractive for continuously moving model-layer data for every generated token. llama.cpp RPC model splitting is still useful when a model simply will not fit on one node, but the preferred architecture is independent workers.

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the detailed design.

## Repository layout

```text
LowPowerLLMCluster/
├── README.md                 plain-language project overview
├── PARTS.md                  generated current parts/pricing table
├── data/
│   └── parts.json            machine-readable source of truth
├── docs/
│   ├── PROJECT_CHARTER.md    mission and hardware scope
│   ├── GUARDRAILS.md         evidence and anti-drift rules
│   ├── ARCHITECTURE.md       worker/router design
│   ├── MODEL_PLACEMENT.md    RAM/model placement strategy
│   ├── NETWORKING.md         2.5/10GbE reasoning
│   ├── POWER.md              efficiency strategy
│   ├── ACCELERATORS.md       NPU/TPU/ASIC/FPGA/EOL accelerator strategy
│   ├── ROADMAP.md            software/hardware roadmap
│   ├── SOURCING.md           seller questions/checklist
│   └── SOURCES.md            manufacturer + marketplace sources
├── specs/                    catalog, benchmark, scoring and agent workflow specs
├── .agents/skills/           reusable agent procedures
├── src/lowpower_llm_cluster/
│   ├── catalog.py
│   ├── scoring.py
│   └── cli.py
├── scripts/
│   ├── check_staleness.py
│   ├── render_parts_table.py
│   └── validate_catalog.py
└── tests/
```

## Use the planner

Python 3.12+:

```bash
python -m pip install -e .
llm-cluster rank
```

Example BOM:

```bash
llm-cluster bom \
  node-huake-7735u-barebone \
  node-huake-7735u-barebone \
  node-tds-8845hs-32g-1t \
  net-edup-8x25gbe
```

The score is deliberately a **planning heuristic**, not a fake benchmark. Once real machines are tested, the project should rank hardware using measured prompt tokens/s, generation tokens/s, watts, tokens/joule and total cost.

## Example first cluster

A cost-focused starting point using current listing snapshots:

```text
         ┌──────────────────────────────────────────┐
         │        SMALL DISTRIBUTED LLM BOX         │
         └──────────────────────────────────────────┘

       2x Ryzen 7735U workers     $330 advertised
       1x Ryzen 8845HS worker     $206-220 advertised
       1x 8-port 2.5GbE switch    $19.90-30 advertised
                                  ──────────────────
       compute/network subtotal   $555.90-580 USD

       + RAM upgrades where needed
       + SSDs where needed
       + shipping/tax/duties
       + cables/mounting
```

The 7735U nodes can handle low-cost background or smaller-model work. The 8845HS can take harder coding/general requests. Later, add a high-memory 8745HS/OcuLink node instead of replacing the whole cluster.

## Next milestones

1. Benchmark real candidate boards using the same GGUF models and llama.cpp build.
2. Measure wall power at idle and generation load.
3. Calculate **tokens/joule** and **tokens per dollar**.
4. Build automatic node discovery and hardware inventory.
5. Add an OpenAI-compatible router.
6. Add automatic model placement and fallback.
7. Add a dashboard showing nodes, models, temperatures, power, throughput and current hardware pricing.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

## Data quality

There are two kinds of facts in this repo:

**Manufacturer facts** — CPU cores, memory support and TDP envelopes should come from AMD or another hardware manufacturer.

**Marketplace facts** — price, MOQ, included RAM/SSD, ports and seller claims are snapshots from marketplace listings and must be rechecked before purchase.

This separation is intentional. A $206 listing is interesting, but it should never become a trusted hardware specification just because it is cheap.
