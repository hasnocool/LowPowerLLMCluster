# Market Intelligence Specification

v0.5 adds a market-evidence layer around the catalog. It does not replace curated hardware records.

## Pipeline

```text
source adapters -> raw listings -> catalog match -> configuration confidence
                -> immutable observations -> price history
                -> currency/shipping/tax/duty model -> Canadian landed cost

vendor/community benchmark source -> normalized performance evidence -> catalog-linked evidence
```

## Product discovery

Discovery adapters are asynchronous. Network implementations MUST use non-blocking clients; blocking SDK/file operations MUST be isolated with `asyncio.to_thread` rather than blocking the event loop. Adapters return normalized `Listing` objects. Source-specific HTML/API fields stay inside adapters.

The initial `JsonFeedAdapter` is deliberately deterministic: it provides a fixture/import contract while live retailer adapters are added independently. Discovery must never invent a SKU, price, shipping charge, configuration, seller, or availability state.

## Price history

Price history is append-only at the observation level and deduplicated by source, source listing ID, observation time, price and currency. A listing can disappear and later return without erasing its history.

Future source adapters should record listing availability/disappearance as explicit observations rather than deleting history.

## Exact SKU/configuration confidence

Matching has two independent components:

- SKU/title identity confidence.
- Configuration agreement for fields actually present in both the catalog and listing.

CPU theoretical maximum memory is never treated as installed/configured RAM. Missing configuration evidence reduces certainty instead of being guessed.

Confidence labels are `unknown`, `low`, `medium`, `high`, and `exact`.

## CAD / Canadian landed cost

FX data is an evidence input, not a hard-coded constant. `data/market/fx-cad.json` starts with CAD only and requires a sourced rate before converting another currency.

The landed-cost calculator exposes item price, shipping, duty, brokerage and tax separately. Tax/duty/brokerage defaults are planning inputs, not claims about a shipment's tariff classification. Users must verify the exact province, origin, HS classification and courier charges before purchase.

## Performance ingestion

Performance records require:

- catalog `part_id`;
- source type and source URL;
- exact model/model variant where known;
- runtime/backend;
- workload/phase;
- metric, numeric value and unit.

Accepted source types follow `specs/EVIDENCE.md`: `measured_local`, `community_measured`, `vendor_measured`, `derived_estimate`, `spec_based_estimate`, and `unknown`.

TOPS/TFLOPS are not converted into tokens/sec. Multiple incompatible models, runtimes or workload phases are not averaged together. Confidence describes evidence quality, not benchmark speed.
