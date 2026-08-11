# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, dev boards, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty boards such as AMD BC-250, and interesting decommissioned accelerators.

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
```

The source-adapter interface is async-first and uses `httpx.AsyncClient` for live network access. Blocking filesystem work stays off the event loop.

### Autonomous refresh

Named refresh profiles live in `data/market/profiles.json`. They combine source coverage, queries, retry/backoff, staleness thresholds, FX refresh and report generation:

```bash
llm-cluster-refresh run daily-market
llm-cluster-refresh run weekly-deep-scan
llm-cluster-refresh health
llm-cluster-refresh stale --hours 72
llm-cluster-refresh reports
```

Transient HTTP/network failures are retried with exponential backoff and jitter; numeric `Retry-After` is honored for rate-limited sources. Permanent client errors are not retried blindly. Every run records source health/history, and a failed source cannot manufacture disappearance events.

`.github/workflows/autonomous-refresh.yml` schedules daily and weekly refresh profiles and can also be triggered manually. Optional Mouser/DigiKey/eBay credentials come from repository secrets; public manufacturer discovery and Bank of Canada FX work without those credentials. Updated market evidence and `reports/current/` are committed only when data changes.

Active listings that have not been reconfirmed within the profile threshold are surfaced as **stale warnings**. Stale does not mean sold, disappeared or invalid; history remains intact.

### Live sources

Current source adapters:

- public manufacturer product pages with schema.org `Product` / `Offer` JSON-LD;
- Mouser Search API;
- DigiKey Product Information V4 with CA/CAD locale defaults;
- eBay Browse API using the Canadian marketplace;
- deterministic JSON feed imports for fixtures, exports and future collectors.

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

The project **will not manufacture tokens/sec** from TOPS, TFLOPS, memory bandwidth, core count or TDP. v0.5 performance imports require the source URL, exact model/variant where known, runtime/backend, workload/phase, metric and unit.

Compatible aggregation is deliberately strict: records with different model variants, quantization, runtime/version/backend, workload phase, units, context dimensions or hardware configuration are kept in separate groups instead of being averaged into a misleading number.

The evidence store now includes exact-product Turing RK1 measurements plus exact Jetson Orin Nano Super community/vendor measurements. Jetson internal-rail energy measurements retain their published power scope and are not relabeled as complete-node tokens/joule.

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
llm-cluster rank
llm-cluster list --llm-only --max-price 250
llm-cluster list --llm-only --min-memory 32 --sort price
llm-cluster show special-amd-bc250-16g
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## Repository map

- `data/catalog/` — curated hardware catalog fragments.
- `data/market/sources.json` — source configuration without secrets.
- `data/market/profiles.json` — named autonomous polling profiles.
- `data/market/price-history.json` — append-only listing/price observations.
- `data/market/listing-state.json` — listing lifecycle events.
- `data/market/source-health.json` — generated source health/history after autonomous runs.
- `data/market/fx-cad.json` / `fx-history.json` — sourced CAD FX evidence.
- `data/evidence/performance.json` — sourced performance evidence.
- `reports/current/` — automatically regenerated current-market reports.
- `docs/AUTONOMOUS_REFRESH.md` — retry, health, stale and scheduling behavior.
- `specs/MARKET_INTELLIGENCE.md` — discovery, pricing, Canadian cost and performance-ingestion contract.
- `benchmarks/` — optional local measurement tooling.
- `PARTS.md` — deterministic human-readable catalog view.

## Design rule

The catalog is the durable product identity layer. Listings, prices, exchange rates and benchmarks are evidence with timestamps and provenance. Evidence may strengthen or weaken a buying recommendation, but it must not silently rewrite a product into a different SKU/configuration.
