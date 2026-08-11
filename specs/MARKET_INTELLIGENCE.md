# Market Intelligence Specification

v0.5 adds a market-evidence layer around the catalog. It does not replace curated hardware records.

## Pipeline

```text
manufacturer JSON-LD / Mouser / DigiKey / eBay / fixture feeds
                         │
                         ▼
               normalized listings
                         │
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
    SKU/config      seller/source     lifecycle state
    confidence       confidence      seen/gone/returned
          │              │               │
          └──────────────┼───────────────┘
                         ▼
                   price history
                         │
          Bank of Canada FX snapshots
                         │
                         ▼
               Canadian landed cost

vendor/community benchmark sources
                         │
                         ▼
                normalized evidence
                         │
                         ▼
          compatibility-signature groups
```

## Real discovery sources

Network adapters use `httpx.AsyncClient` and must not block the event loop.

Current adapters:

- `ManufacturerJsonLdAdapter`: public manufacturer product pages that expose schema.org `Product` / `Offer` JSON-LD.
- `MouserAdapter`: Mouser Search API; credential from `MOUSER_API_KEY`.
- `DigiKeyAdapter`: DigiKey Product Information V4; credentials from `DIGIKEY_CLIENT_ID` and `DIGIKEY_ACCESS_TOKEN`, with CA/CAD locale defaults.
- `EbayBrowseAdapter`: eBay Browse API using application OAuth from `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`; defaults to the Canadian marketplace.
- `JsonFeedAdapter`: deterministic import boundary for fixtures, exports and future collectors.

Credential values MUST NOT be committed. `data/market/sources.json` contains only source URLs, documentation links and credential environment-variable names.

A missing credential disables that source cleanly. A failed source request is recorded as failed for that discovery run and MUST NOT be treated as evidence that its listings disappeared.

Discovery must never invent a SKU, price, shipping charge, configuration, seller, stock state or availability state.

## Listing disappearance / reappearance

`data/market/listing-state.json` tracks listing state separately from price history.

Disappearance is inferred only when all of the following are true:

1. the source poll succeeded;
2. the prior listing was active;
3. the listing is absent now;
4. the poll uses the same normalized query/watch scope as the observation that established the listing.

This prevents an API outage or a narrower/different search from generating false sold-out/disappeared events.

Lifecycle events are `discovered`, `disappeared`, and `reappeared`. History is not deleted when a listing disappears.

## Price history

Price history is append-only at the observation level and deduplicated by source, source listing ID, observation time, price and currency. A listing can disappear and later return without erasing its history.

Each price observation may include two independent confidence signals:

- exact-SKU/configuration confidence;
- seller/source confidence.

These must never be collapsed into one score: a trustworthy seller can still list the wrong configuration, and an exact configuration can still come from a weak seller.

## Exact SKU/configuration confidence

Matching has two independent components:

- SKU/title identity confidence.
- Configuration agreement for fields actually present in both the catalog and listing.

CPU theoretical maximum memory is never treated as installed/configured RAM. Missing configuration evidence reduces certainty instead of being guessed.

Confidence labels are `unknown`, `low`, `medium`, `high`, and `exact`.

## Seller/source confidence

Source class provides the baseline:

- manufacturer;
- authorized distributor;
- structured marketplace;
- unknown.

Where a marketplace exposes reputation data, seller feedback percentage, feedback volume and top-rated status may strengthen or weaken the source confidence. These fields describe transaction/source confidence, not product compatibility or benchmark quality.

## CAD / Canadian landed cost

FX data is an evidence input, not a hard-coded constant.

`llm-cluster-market refresh-fx` retrieves current daily currency observations from the Bank of Canada Valet API and writes:

- current conversion snapshot to `data/market/fx-cad.json`;
- append-only snapshots to `data/market/fx-history.json`.

Rates are represented as CAD per unit of source currency. The landed-cost calculator exposes item price, shipping, duty, brokerage and tax separately. Tax/duty/brokerage inputs are planning assumptions, not claims about a shipment's tariff classification. Users must verify the exact province, origin, HS classification and courier charges before purchase.

## Performance ingestion and compatible aggregation

Performance records require:

- catalog `part_id`;
- source type and source URL;
- exact model/model variant where known;
- runtime/backend;
- workload/phase;
- metric, numeric value and unit.

Accepted source types follow `specs/EVIDENCE.md`: `measured_local`, `community_measured`, `vendor_measured`, `derived_estimate`, `spec_based_estimate`, and `unknown`.

Default aggregation includes measured local/community/vendor records only. Records are grouped by a compatibility signature containing model, variant/quantization/hash, runtime/version/backend, workload, metric/unit, context/prompt/generation dimensions, batch size and hardware configuration where present.

Only records with the exact same signature can contribute to the same median/range/mean group. A Q4 decode result cannot be averaged with Q8, prefill, another model, another unit or a materially different runtime/hardware configuration.

TOPS/TFLOPS are never converted into tokens/sec. Confidence describes evidence quality, not benchmark speed.
