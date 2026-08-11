# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, **discrete GPUs**, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

You do **not** need to own every product. The job of the catalog is to answer:

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

Current market snapshot: **August 10, 2026**. Prices and variants change; verify exact SKUs before purchasing.

## v0.5 market intelligence

v0.5 turns the static catalog into a time-aware research pipeline without allowing volatile listings to overwrite curated hardware facts:

```text
manufacturer pages     distributors       marketplaces
 JSON-LD offers       Mouser / DigiKey       eBay CA
       │                    │                   │
       └────────────────────┼───────────────────┘
                            ▼
                    async discovery
                            │
                            ▼
                   normalized listing
                            │
          ┌─────────────────┼───────────────────┐
          ▼                 ▼                   ▼
     SKU/config          seller/source      lifecycle
      confidence          confidence      seen/gone/back
          │                 │                   │
          └─────────────────┼───────────────────┘
                            ▼
                       price history
                            │
                 Bank of Canada FX
                            │
                            ▼
                 Canadian landed cost
                            │
                            ▼
                  current CAD reports
                            │
                            ▼
                   change intelligence
                            │
                            ▼
              BUY / WATCH / IGNORE / EXPERIMENTAL
```

The source-adapter interface is async-first and uses `httpx.AsyncClient` for live network access. Blocking filesystem work stays off the event loop.

## Decision quality

Every autonomous refresh now generates a ranked decision report:

- `reports/current/daily-recommendations.md`
- `reports/current/daily-recommendations.json`

The deal score is intentionally a **buying-decision score, not a performance benchmark**. Current weighting is:

```text
35%  price-history position
25%  conservative model-capacity fit
20%  evidence confidence
10%  opportunity freshness
10%  price stability / volatility
```

The engine also tracks:

- new native-currency all-time lows;
- recent price trend;
- price volatility;
- decision-confidence score;
- internal opportunity freshness/expiry;
- prioritized P1-P4 change alerts;
- ranked `Buy`, `Watch`, `Experimental`, and `Ignore` candidates.

An opportunity expiry is a freshness deadline unless the seller provides a parseable end time. It is **not** a prediction that the product will definitely sell or disappear.

The model-fit score is only a memory-capacity screen for 7B/14B/32B/70B Q4 planning presets with explicit headroom. It never manufactures tokens/sec.

```bash
llm-cluster-refresh recommendations
llm-cluster-refresh alerts
llm-cluster-refresh watchlists
llm-cluster-refresh budgets
```

See `docs/DECISION_QUALITY.md` and `specs/SCORING.md`.

## Discrete GPUs are first-class sourcing targets

GPUs now have their own `gpu_accelerator` catalog category rather than being omitted from the sourcing universe.

Initial reference families include:

- NVIDIA GeForce RTX 5060 Ti 16GB;
- NVIDIA GeForce RTX 3090 24GB used-market watch;
- AMD Radeon RX 9070 / RX 9070 XT 16GB;
- Intel Arc B580 12GB;
- Intel Arc A770 16GB used/discounted watch.

Both autonomous market profiles explicitly search GPU listings. A dedicated `gpu-value` watchlist tracks 12GB+ discrete cards independently from tiny low-power nodes and experimental accelerators.

For GPUs:

- fixed VRAM is valid model-fit capacity evidence;
- board-partner SKU/condition stays separate from the reference GPU identity;
- CUDA, ROCm/Vulkan and oneAPI/SYCL maturity are tracked explicitly;
- TGP/TBP is board power, **not complete-node watts**;
- no GPU TOPS/TFLOPS number is converted into fake LLM throughput.

See `docs/GPUS.md`.

### Autonomous refresh

Named refresh profiles live in `data/market/profiles.json`. They combine source coverage, queries, retry/backoff, staleness thresholds, source budgets, FX refresh, change intelligence and report generation:

```bash
llm-cluster-refresh run daily-market
llm-cluster-refresh run weekly-deep-scan
llm-cluster-refresh health
llm-cluster-refresh stale --hours 72
llm-cluster-refresh reports
llm-cluster-refresh recommendations
llm-cluster-refresh alerts
llm-cluster-refresh watchlists
llm-cluster-refresh budgets
```

Transient HTTP/network failures are retried with exponential backoff and jitter; numeric `Retry-After` is honored for rate-limited sources. Permanent client errors are not retried blindly. Every run records source health/history, and a failed or budget-disabled source cannot manufacture disappearance events.

`.github/workflows/autonomous-refresh.yml` schedules daily and weekly refresh profiles and can also be triggered manually. Optional Mouser/DigiKey/eBay credentials come from repository secrets; public manufacturer discovery and Bank of Canada FX work without those credentials. Updated market evidence, intelligence state and `reports/current/` are committed only when data changes.

Active listings that have not been reconfirmed within the profile threshold are surfaced as **stale warnings**. Stale does not mean sold, disappeared or invalid; history remains intact.

### Live sources

Current source adapters:

- public manufacturer product pages with schema.org `Product` / `Offer` JSON-LD;
- Mouser Search API;
- DigiKey Product Information V4 with CA/CAD locale defaults;
- eBay Browse API using the Canadian marketplace;
- deterministic JSON feed imports for fixtures, exports and future collectors.

Official GPU specification/reference URLs are also retained in `data/market/sources.json`, while current seller prices remain market observations rather than catalog facts.

Credentials come from environment variables and are **never** stored in `data/market/sources.json`:

```bash
export MOUSER_API_KEY='...'
export DIGIKEY_CLIENT_ID='...'
export DIGIKEY_ACCESS_TOKEN='...'
export EBAY_CLIENT_ID='...'
export EBAY_CLIENT_SECRET='...'
```

Missing credentials simply disable that source. A failed API request also cannot create fake listing-disappearance events.

Examples:

```bash
llm-cluster-market discover --source manufacturer --query "Jetson Orin Nano"
llm-cluster-market discover --source ebay --query "GeForce RTX 3090 24GB"
llm-cluster-market discover --source ebay --query "Intel Arc A770 16GB"
llm-cluster-market discover --source mouser --source digikey --query "RK3588"
llm-cluster-market discover --source ebay --query "Alveo U50"
llm-cluster-market discover --feed listings.json --query "Ryzen 8845HS"
llm-cluster-market refresh-fx --currency USD --currency EUR
llm-cluster-market history special-amd-bc250-16g
llm-cluster-market landed listing.json --tax-rate 0.12
llm-cluster-market ingest-performance performance-records.json
llm-cluster-market aggregate-performance special-amd-bc250-16g
llm-cluster-market report under-250
```

`data/market/listing-state.json` records `discovered`, `disappeared`, and `reappeared` events. Disappearance is only inferred after a successful poll of the **same source and query scope**, so changing the search query cannot make unrelated products appear to vanish.

`llm-cluster-market refresh-fx` uses the Bank of Canada Valet API and stores both the current snapshot and append-only FX history. Landed cost keeps item, shipping, duty, brokerage and tax separate because actual Canadian customs treatment depends on the shipment, province, origin, courier and tariff classification.

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

The project **will not manufacture tokens/sec** from TOPS, TFLOPS, memory bandwidth, core count or TDP/TGP/TBP. v0.5 performance imports require the source URL, exact model/variant where known, runtime/backend, workload/phase, metric and unit.

Compatible aggregation is deliberately strict: records with different model variants, quantization, runtime/backend, workload phase, units, context dimensions or hardware configuration are kept in separate groups instead of being averaged into a misleading number. Runtime-version changes may be compared by the change-intelligence layer only when the remaining compatibility dimensions match, so software regressions can be detected without averaging unlike workloads.

The evidence store includes exact-product Turing RK1, Jetson Orin Nano Super and stock 24-CU BC-250 measurements. Jetson internal-rail energy measurements retain their published power scope and are not relabeled as complete-node tokens/joule.

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
 compare with trustworthy RAM / VRAM
```

This answers **"is this worth investigating for a model this size?"** It does *not* predict speed and cannot know exact KV-cache/runtime overhead without a specific model/backend.

Example:

```bash
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## Memory semantics matter

A barebone with a CPU that theoretically supports 256GB does **not** contain 256GB. The catalog separates:

- `memory_capacity_gb` — RAM/VRAM actually included or fixed in that referenced configuration;
- `max_memory_gb` — verified maximum for the board/product, when known;
- `cpu_max_memory_gb` — processor-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

For discrete GPUs, `memory_capacity_gb` is fixed VRAM and `memory_config_status` must be `fixed`.

v0.5 applies the same rule to listing matching: CPU-theoretical RAM does not increase configuration confidence.

## Browse the catalog

```bash
python -m pip install -e .
llm-cluster rank
llm-cluster list --llm-only --max-price 250
llm-cluster list --category gpu_accelerator --sort price
llm-cluster list --llm-only --min-memory 24 --sort price
llm-cluster show gpu-nvidia-rtx-3090-24g
llm-cluster fit gpu-nvidia-rtx-5060-ti-16g --params-b 14 --bits 4
```

## Repository map

- `data/catalog/` — curated hardware catalog fragments, including `gpus.json`.
- `data/market/sources.json` — source configuration and official reference URLs without secrets.
- `data/market/profiles.json` — named autonomous polling profiles, including GPU search queries.
- `data/market/watchlists.json` — configurable market watchlists, including `gpu-value`.
- `data/market/price-history.json` — append-only listing/price observations.
- `data/market/listing-state.json` — listing lifecycle events.
- `data/market/source-health.json` — generated source health/history after autonomous runs.
- `data/market/fx-cad.json` / `fx-history.json` — sourced CAD FX evidence.
- `data/evidence/performance.json` — sourced performance evidence.
- `reports/current/` — automatically regenerated market, change and recommendation reports.
- `docs/AUTONOMOUS_REFRESH.md` — retry, health, stale and scheduling behavior.
- `docs/CHANGE_INTELLIGENCE.md` — alert/watchlist/change semantics.
- `docs/DECISION_QUALITY.md` — deal scoring, price trend/volatility, expiry and recommendation classes.
- `docs/GPUS.md` — GPU sourcing, VRAM, software and power-boundary rules.
- `specs/MARKET_INTELLIGENCE.md` — discovery, pricing, Canadian cost and performance-ingestion contract.
- `specs/SCORING.md` — catalog and decision scoring contract.
- `benchmarks/` — optional local measurement tooling.
- `PARTS.md` — deterministic human-readable catalog view.

## Design rule

The catalog is the durable product identity layer. Listings, prices, exchange rates and benchmarks are evidence with timestamps and provenance. Evidence may strengthen or weaken a buying recommendation, but it must not silently rewrite a product into a different SKU/configuration.
