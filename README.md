# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

You do **not** need to own every product. The catalog exists to answer:

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

The repository keeps exact market observations separate from derived estimates. Prices and variants change; verify exact SKUs before purchasing.

## The project in one picture

```text
                     PRODUCT DISCOVERY
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
 JSON / JSON-LD       manual research       imports
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                  NORMALIZE + CONFIDENCE
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
      listing history   exact SKU      hardware shape
      price/stock       confidence     RAM/DC/cooling
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                     PRODUCT CATALOG
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       reports          model fit        evidence
      /dashboard        capacity         provenance
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    BUYING SHORTLIST
```

## Evidence, not pretend precision

A product can be valuable even when no local benchmark exists. Performance evidence is labelled by provenance:

```text
measured_local       direct project measurement
community_measured   identifiable third-party measurement
vendor_measured      vendor workload measurement

derived_estimate     transformation of measured evidence
spec_based_estimate  weak planning clue only
unknown              valid when evidence does not exist
```

The project **will not manufacture tokens/sec** from TOPS, TFLOPS, memory bandwidth, core count or TDP.

v0.5 adds multi-source ranges, but a range is emitted only when at least two independent measured records share the same hardware/model/runtime/workload/metric/quantization/context signature. A single vendor result stays a single vendor result.

## Fast, bounded end-to-end discovery

The discovery path is designed to run efficiently on laptop/mini-PC class systems while still scaling to many sources:

```text
source queue
   │
   ├─ agent worker ─┬─ URL subworker ─┐
   ├─ agent worker ─┼─ URL subworker ─┼─> pooled aiohttp connections
   └─ agent worker ─┴─ URL subworker ─┘       │
                                              ▼
                                    off-loop parse/normalize
                                              │
                                ┌─────────────┴─────────────┐
                                ▼                           ▼
                         normalized output          SQLite writer actor
                                                   WAL + batched writes
```

Important properties:

- native async HTTP through a shared `aiohttp.ClientSession` rather than thread-wrapped `urllib`;
- bounded source-agent workers and bounded per-source URL subworkers;
- global and per-host connection limits with keep-alive reuse;
- bounded queues provide backpressure instead of unbounded task creation;
- JSON/HTML parse and normalization work stays off the event loop when it can become material;
- SQLite owns one persistent connection on one dedicated writer thread and batches mutations;
- normalization and history persistence run concurrently after discovery;
- atomic JSON output avoids partially-written refresh snapshots;
- runtime telemetry records stage latency, per-source timing, requests, bytes and max in-flight HTTP work;
- CI rejects obvious event-loop blocking regressions in the end-to-end path.

The defaults are conservative. Configure worker levels independently:

```json
{
  "agent_workers": 4,
  "subworkers_per_agent": 4,
  "normalize_workers": 2,
  "queue_size": 64,
  "http_concurrency": 16,
  "http_per_host": 4,
  "timeout_s": 20
}
```

See [docs/CONCURRENCY.md](docs/CONCURRENCY.md) for the worker hierarchy and tuning guidance.

```bash
cp config/discovery.example.json config/discovery.local.json
# Edit sources; remove the example.invalid feed before running.
llm-cluster discover --config config/discovery.local.json
```

History defaults to `results/catalog-history.sqlite3` and the latest normalized observations to `results/discovery-latest.json`.

## Memory semantics matter

A barebone with a CPU that theoretically supports 256GB does **not** contain 256GB. The catalog separates:

- `memory_capacity_gb` — RAM actually included/fixed in the referenced configuration;
- `max_memory_gb` — verified maximum for the actual board/product when known;
- `max_memory_source_url` / `max_memory_verified_on` — evidence for that board maximum;
- `cpu_max_memory_gb` — processor-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

Board-level maximums can therefore be trusted more strongly than CPU-only limits without pretending every legacy record is already verified.

## Browse, report and compare

```bash
python -m pip install -e .

llm-cluster rank
llm-cluster list --llm-only --max-price 250
llm-cluster list --llm-only --min-sku-confidence 0.70 --sort price

llm-cluster report best_under_200
llm-cluster report high_memory_bargains
llm-cluster report low_power_nodes
llm-cluster report weird_hardware
llm-cluster report eol_bargains

llm-cluster dashboard --output results/catalog-dashboard.html
```

The dashboard supports budget, RAM, published-power-boundary and risk filters, side-by-side selection, and browser-saved filters. Power labels retain their scope; a processor TDP is never shown as wall power.

## Safe model-fit presets

Model fit is a **capacity screen**, not a speed predictor:

```bash
llm-cluster fit special-amd-bc250-16g --preset 14b-q4
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

Presets cover representative 1B, 3B, 7B, 14B, 32B and 70B quantized classes. Runtime overhead and KV cache remain model/backend specific and are called out in the result.

## CAD / Canada landed-cost planning

Landed cost uses an **explicit FX snapshot** rather than silently fetching a rate, which makes saved calculations reproducible:

```bash
llm-cluster landed-cost \
  --price 220 --currency USD \
  --fx-rate 1.37 --fx-as-of 2026-08-12 \
  --province BC --shipping 25 --duty-rate 0.00 --brokerage-cad 15
```

This is a planning estimate, not a customs/tax guarantee. Shipping, duty classification, brokerage and tax assumptions are printed with the result.

## Sourced performance records

Performance records preserve model/runtime/workload provenance rather than attaching a naked throughput number to hardware.

```bash
llm-cluster performance-range data/performance/my-records.json \
  --hardware-id node-example \
  --model Example-7B \
  --runtime llama.cpp \
  --workload-class llm_decode \
  --metric tokens_per_second
```

Specialist vision/audio/embedding/reranking records are kept out of the LLM range bucket. `data/performance/hailo10h-qwen2-vendor.json` is an example of a single vendor-provenance record; by design it cannot create a multi-source confidence range by itself.

## Hardware families

| Class | Examples | Why track it? |
|---|---|---|
| low-power x86 | Ryzen 7735U/8845HS, N100 | common Linux ecosystem, replaceable RAM on many models |
| high-memory mobile boards | 8745HS/HX370/7945HX | dense CPU/APU compute with laptop-class efficiency |
| unusual APU | AMD BC-250 | cheap unified GDDR6 and interesting Vulkan potential |
| ARM/SBC | RK3588, RK3576, Jetson Orin | low power and compact always-on nodes |
| GenAI NPU/TPU | Hailo-10H, SOPHGO | real purpose-built transformer paths at low power |
| AI ASIC | Tenstorrent | interesting accelerator architecture and fast local memory |
| FPGA/adaptive | Kria, Versal, Alveo | custom low-precision research potential |
| specialist | Coral, MemryX | fixed inference can keep larger nodes asleep |
| decommissioned | Alveo/NCS2/etc. | liquidation pricing can create strange bargains |

See **[PARTS.md](PARTS.md)** for the canonical catalog. `data/discovery/watchlist.json` holds newly researched targets that still need exact price/SKU verification before promotion.

## Catalog score vs performance

`llm-cluster rank` is deliberately shopping-oriented. It considers price, memory evidence, published power hints, software maturity, lifecycle, risk, and—when present—seller/source/SKU confidence.

```text
CATALOG SCORE                   PERFORMANCE EVIDENCE
─────────────                   ────────────────────
price                           measured tokens/sec
RAM included/potential          exact model/runtime/workload
published power scope           complete-node watts when measured
software maturity               tokens/joule when comparable
seller/SKU confidence           independent source provenance
risk / availability             measured range confidence

            kept as separate dimensions
```

A high catalog score means **"worth investigating"**, not "fastest LLM hardware."

## Optional benchmark subsystem

The `llm-cluster-bench` harness remains available for local or contributed measurements. It is evidence tooling, not a catalog-release gate.

See [docs/BENCHMARK_HARNESS.md](docs/BENCHMARK_HARNESS.md).

## Repository layout

```text
LowPowerLLMCluster/
├── config/discovery.example.json    discovery + worker configuration
├── data/parts.json                  canonical catalog manifest
├── data/catalog/                    reviewed product records by family
├── data/discovery/                  researched promotion/watch targets
├── data/performance/                sourced performance evidence
├── PARTS.md                         generated canonical catalog
├── specs/HARDWARE_CATALOG.md        product data contract
├── specs/EVIDENCE.md                provenance + estimation rules
├── specs/discovery-config.schema.json
├── specs/performance-record.schema.json
├── docs/SOURCING.md                 source/history/promotion workflow
├── docs/CONCURRENCY.md              async worker/backpressure architecture
├── src/lowpower_llm_cluster/        discovery, runtime, history, planner, reports, UI
├── benchmarks/                      optional benchmark profiles
└── results/                         generated local outputs
```

## Next priorities

See **[TODO.md](TODO.md)**. The next speed/efficiency work is conditional HTTP caching, retry/backoff and rate-limit handling, adaptive concurrency, long-running pool reuse, load benchmarks, and streaming persistence. Accuracy work continues with source-specific marketplace adapters, promotion diffs, board-memory/spec backfilling, and independent performance evidence.

## Data quality rule

**Measured ≠ published ≠ community-reported ≠ derived ≠ speculative.**

The distinction is a feature of the project, not an inconvenience.
