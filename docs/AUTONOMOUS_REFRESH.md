# Autonomous Market Refresh

v0.5 can refresh market evidence without turning volatile listings into catalog facts.

## Profiles

`data/market/profiles.json` defines named refresh jobs. Profiles select sources, queries, retry policy, staleness threshold, FX currencies and whether current-market reports are regenerated.

```bash
llm-cluster-refresh run daily-market
llm-cluster-refresh run weekly-deep-scan
llm-cluster-refresh health
llm-cluster-refresh stale --hours 72
llm-cluster-refresh reports
```

## Retry and rate-limit behavior

Transient network failures, HTTP 408/425/429 and common 5xx responses are retried with exponential backoff and jitter. `Retry-After` is honored when it contains a numeric delay. Permanent 4xx errors are not retried blindly.

Retries wrap a source poll, while source health is recorded separately. A failed source does not create listing-disappearance events because disappearance is only inferred from sources that completed successfully in the same query scope.

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

## Automatic FX and reports

Profiles can refresh Bank of Canada FX immediately after source polling and then regenerate `reports/current/`. This ordering makes reports use the newest successfully sourced FX snapshot available to the run.

Generated reports include machine-readable JSON and human-readable Markdown for the established buying views. Catalog midpoint fallback prices remain explicitly distinguishable from live listing prices.

## GitHub Actions schedule

`.github/workflows/autonomous-refresh.yml` runs:

- `daily-market` every day;
- `weekly-deep-scan` every Sunday;
- either profile manually through `workflow_dispatch`.

The workflow can use optional repository secrets for Mouser, DigiKey and eBay. Public manufacturer discovery and Bank of Canada FX do not depend on those credentials. Refreshed market evidence and generated reports are committed only when files changed.

## Benchmark evidence rule

Autonomous market refresh does not copy benchmark numbers between products. Exact hardware identity remains mandatory. For example, Turing RK1 measurements stay on the RK1 record, and Jetson Orin Nano Super measurements stay on the exact Jetson record even when another board uses related silicon.

Community power metrics must preserve their measurement boundary. Internal Jetson rail telemetry may be useful evidence, but it is not relabeled as complete-node wall-input energy.
