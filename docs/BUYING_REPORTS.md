# CAD Buying Reports

The v0.5 market layer can turn catalog + live-market evidence into shopping-oriented reports without pretending every price is equally current.

## Reports

```bash
llm-cluster-market report under-100
llm-cluster-market report under-250
llm-cluster-market report under-500
llm-cluster-market report 32gb-plus
llm-cluster-market report low-power
llm-cluster-market report weird-bargains
llm-cluster-market report eol-bargains
llm-cluster-market report measured-evidence
llm-cluster-market report all
```

Add `--json` for machine-readable output.

## Price hierarchy

Reports prefer an active, catalog-matched listing from `data/market/price-history.json`. If no active listing exists, the report may use the catalog midpoint as a planning fallback.

Every row exposes a price basis:

- `live_listing+shipping+tax` — current active listing observation plus known shipping and the selected planning tax rate;
- `catalog_midpoint+tax` — catalog snapshot fallback, not a live quote;
- `unpriced` — required FX or price evidence is unavailable.

A missing USD/CAD rate does not cause the tool to invent one. Run `llm-cluster-market refresh-fx --currency USD` before expecting USD catalog fallbacks to appear in CAD reports.

The default 12% tax rate is a planning convenience for a BC-style view, not a customs ruling. Duty, brokerage, origin, province and tariff classification remain shipment-specific.

## Market confidence

For live listing rows, market confidence combines:

- exact-SKU/configuration confidence (70% weight);
- seller/source confidence (30% weight).

A catalog fallback is labelled `static` rather than receiving a fake live-market confidence score.

## Benchmark evidence

The report includes the count of compatible measured-performance groups linked to the exact catalog product. Benchmark evidence is not transferred across different boards merely because they share a CPU/SoC.

Example: the Turing RK1 32GB has vendor-published RK3588/llama.cpp measurements tied to that exact product. Orange Pi 5 Plus and Radxa ROCK 5 remain separate candidates until board-specific measurements are available.

## Intended use

These reports are shortlist generators. A low CAD price does not prove good inference performance, and a measured benchmark does not prove a seller/listing is trustworthy. Price, configuration confidence, seller confidence, software maturity, power, memory and performance evidence remain separate dimensions so a later scoring layer can combine them transparently.
