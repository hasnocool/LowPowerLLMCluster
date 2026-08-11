# Alerts and Change Intelligence

The change-intelligence layer turns time-series market evidence into a compact set of meaningful deltas. It does not send purchase orders or treat every scrape difference as important.

## Alert types

- `price_drop`: same listing/source price falls beyond the configured percentage threshold.
- `landed_cost_change`: CAD planning cost changes beyond threshold after sourced FX, shipping and tax inputs.
- `stock_return`: a listing previously marked absent reappears in the same source/query scope.
- `new_product`: a new listing appears in a watched scope.
- `benchmark_improvement`: a newer compatible measured result exceeds the prior compatible result by threshold.
- `benchmark_regression`: the same compatibility signature falls by threshold.

## Watchlists

`data/market/watchlists.json` supports matches by exact part ID, category, keyword, source, minimum memory and maximum target power. Every watchlist may override alert thresholds independently.

A watchlist is a filter, not a source of truth. Exact SKU confidence, seller confidence and evidence provenance remain separate.

## Benchmark-change rule

Benchmark deltas require the same:

- catalog part;
- model/model variant;
- quantization and model hash when present;
- runtime and runtime version;
- backend;
- workload/phase;
- metric and unit;
- context/prompt/generation/batch dimensions when present;
- hardware configuration.

Changing stock BC-250 firmware to a 40-CU unlock, changing Q4 to Q8, or comparing prefill with decode creates a different signature and cannot trigger a regression/improvement comparison against the original run.

## Source budgets

Refresh profiles define `source_budgets` with:

- `max_queries_per_run`;
- `daily_request_budget`.

`data/market/source-budgets.json` is runtime state. Budgets reset on a new UTC date. The counter is an intentionally conservative request estimate based on scheduled query work; provider response headers remain authoritative when a live API exposes stricter limits.

Retries still honor transient HTTP failures and numeric `Retry-After`. Budget exhaustion disables that source for the remainder of the profile run rather than turning it into a source failure or fake disappearance event.

## Daily brief

Each successful refresh writes:

- `reports/current/daily-changes.json` — complete machine-readable alert set;
- `reports/current/daily-changes.md` — compact human-readable shortlist of what deserves attention.

Alert fingerprints are retained in `data/market/intelligence-state.json` so the same historical price drop or benchmark delta is not emitted every day.

The report is deliberately concise. Raw price history, source health, listing lifecycle and benchmark records remain available when an alert needs investigation.
