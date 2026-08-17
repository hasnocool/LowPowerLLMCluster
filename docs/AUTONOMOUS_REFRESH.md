# Autonomous Market Refresh

v0.5 can refresh market evidence without turning volatile listings into catalog facts.

## Profiles

`data/market/profiles.json` defines named refresh jobs. Profiles select sources, queries, retry policy, staleness threshold, source budgets, FX currencies and whether current-market reports are regenerated.

The general profiles include **discrete GPU sourcing** alongside mini PCs, SBCs, unusual boards and specialist accelerators. The daily profile tracks common current/used GPU candidates while the weekly deep scan includes broader higher-power and experimental bargains. A separate `gpu-deal-scan` profile keeps high-VRAM workstation/datacenter searches on a narrow eBay-only request budget so those queries do not crowd out the general discovery queues.

```bash
llm-cluster-refresh run daily-market
llm-cluster-refresh run weekly-deep-scan
llm-cluster-refresh run gpu-deal-scan
llm-cluster-refresh health
llm-cluster-refresh stale --hours 72
llm-cluster-refresh reports
llm-cluster-refresh recommendations
llm-cluster-refresh alerts
llm-cluster-refresh watchlists
llm-cluster-refresh budgets
```

## Retry and rate-limit behavior

Transient network failures, HTTP 408/425/429 and common 5xx responses are retried with exponential backoff and jitter. `Retry-After` is honored when it contains a numeric delay. Permanent 4xx errors are not retried blindly.

Retries wrap a source poll, while source health is recorded separately. A failed source does not create listing-disappearance events because disappearance is only inferred from sources that completed successfully in the same query scope.

Each profile also caps queries per run and estimated daily requests per source. If a budget is exhausted, that source is skipped cleanly rather than being treated as a successful empty poll.

## Source health

`data/market/source-health.json` is created/updated by refresh runs and preserves a bounded history of source observations. Per-source state includes:

- last check;
- last successful poll;
- last failure and error;
- last listing count;
- consecutive failure count.

Health describes collection reliability. It is not seller confidence and is not product evidence.

## Stale listings

An active listing becomes *stale* when its `last_seen` timestamp exceeds the profile threshold. Staleness is only a warning that the listing has not been reconfirmed recently. It does not delete the listing, erase price history, or claim the item is sold out.

## Automatic FX, change intelligence and decision reports

Profiles can refresh Bank of Canada FX immediately after source polling and then regenerate `reports/current/`. This ordering makes reports use the newest successfully sourced FX snapshot available to the run.

Each completed profile produces or refreshes:

- established CAD buying reports in JSON and Markdown;
- `daily-changes.json` / `daily-changes.md` for significant watched changes;
- `daily-recommendations.json` / `daily-recommendations.md` for ranked Buy / Watch / Ignore / Experimental decisions.

The decision report uses price-history position, conservative model-capacity fit, confidence, opportunity freshness and price stability. It does not manufacture performance from product specifications. See `docs/DECISION_QUALITY.md`.

Catalog midpoint fallback prices remain explicitly distinguishable from live listing prices. An unpriced product, including an otherwise attractive GPU, cannot become `Buy` solely from specifications.

## GPU refresh behavior

GPU discovery follows the same market rules as every other hardware family:

- the catalog keeps a durable reference GPU identity;
- seller/board-partner listings remain observations;
- exact SKU/condition confidence is separate from the reference product;
- fixed VRAM is valid model-fit capacity evidence;
- board TGP/TBP is not complete-node power;
- current and used-market GPU listings can move among Buy/Watch/Ignore as price and evidence change.

The `gpu-value` watchlist keeps GPU price/stock alerts separate from the <=25W always-on watchlist. Workstation/datacenter GPU watches additionally support `alerts.max_landed_cad`, which emits a one-time `deal_threshold` alert when a listing is first observed below the configured Canadian landed-cost ceiling or crosses down through that ceiling. See `docs/GPU_DEAL_WATCHES.md`.

## GitHub Actions schedule

`.github/workflows/autonomous-refresh.yml` runs:

- `daily-market` every day;
- `gpu-deal-scan` every day on its own low request budget;
- `weekly-deep-scan` every Sunday;
- any profile manually through `workflow_dispatch`.

The workflow can use optional repository secrets for Mouser, DigiKey and eBay. Public manufacturer discovery and Bank of Canada FX do not depend on those credentials. Refreshed market evidence, intelligence state and generated reports are committed only when files changed.

The Actions log prints both the compact change report and the ranked daily recommendation report so a refresh can be reviewed without opening generated files manually.

## Benchmark evidence rule

Autonomous market refresh does not copy benchmark numbers between products. Exact hardware identity remains mandatory. For example, Turing RK1 measurements stay on the RK1 record, Jetson Orin Nano Super measurements stay on the exact Jetson record, and stock BC-250 measurements stay separate from modified/unlocked variants.

The same rule applies to GPUs: a benchmark from one exact GPU/board/runtime configuration must not be copied to another memory variant or board configuration merely because the GPU family name is similar.

Community power metrics must preserve their measurement boundary. Internal rails or GPU board telemetry may be useful evidence, but they are not relabeled as complete-node wall-input energy.
