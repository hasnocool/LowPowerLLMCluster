# Exact Apple configuration and manufacturer support APIs

This layer closes two major evidence gaps in the market/compatibility pipeline.

## Apple marketplace resolution

Apple marketplace listings are enriched before catalog matching. The resolver treats identity, hardware configuration and seller condition as separate evidence classes.

### Exact configuration evidence

The resolver can retain:

- Apple A-number;
- macOS model identifier;
- Apple part/order number when stated;
- M1-M5 chip family and Pro/Max/Ultra suffix;
- installed unified memory;
- SSD/storage capacity;
- screen size;
- explicitly stated CPU core count;
- explicitly stated GPU core count.

`exact_configuration=true` requires identity + chip + RAM + storage and no conflicting evidence. A-number alone does not define RAM, storage or GPU bin. GPU core count is never inferred from an M-series family name.

### Authoritative Apple identifier registry

`data/evidence/apple-identifiers.json` is a data-driven Apple Support identity registry. It currently covers the highest-value Apple-silicon marketplace families across MacBook Air, MacBook Pro, Mac mini and Mac Studio from M1 through the current M5 era.

Apple's model-identification pages publish model identifiers and part-number families such as `MGN63xx/A`; Apple explicitly describes `xx` as the country/region variable. The resolver therefore matches a concrete regional order number such as `MGN63LL/A` against the published family without pretending the region suffix is universal.

Registry records preserve:

- product family and introduced year;
- model identifiers;
- Apple-published part/order-number patterns;
- exact chip identity only when Apple separates the model cleanly;
- chip candidate sets when Apple groups Pro/Max variants under the same part-number family;
- A-numbers only where an Apple Support technical-specification page exposes the regulatory model number;
- Apple Support provenance for both the model/part mapping and, when applicable, the A-number mapping.

The registry intentionally does **not** store build-to-order RAM, SSD capacity, CPU core count or GPU core count. Those facts still need to be explicit in the listing or come from a stronger exact-configuration source.

Examples of the evidence boundary:

- an M1 MacBook Air part-number family can establish `MacBookAir10,1` and M1 because Apple identifies that model directly;
- a 2021 14-inch MacBook Pro order number can establish the 2021 14-inch family, but it does not choose M1 Pro versus M1 Max unless another fact states the chip;
- if a seller calls an Apple-published M1 part number an M2 machine, the resolver records an identity conflict and blocks `exact_configuration`.

The primary Apple Support sources are:

- <https://support.apple.com/en-ca/102869> for MacBook Air model identifiers and part-number families;
- <https://support.apple.com/en-ca/108052> for MacBook Pro model identifiers and part-number families;
- <https://support.apple.com/en-ca/102852> for Mac mini model identifiers and part-number families;
- <https://support.apple.com/en-ca/102231> for Mac Studio model identifiers and part-number families.

Some regional Apple technical-specification pages additionally publish regulatory A-numbers. Those source URLs are retained per registry record rather than generalized to models Apple has not explicitly tied to that number on the cited page.

### Condition evidence

The resolver separately retains seller-stated:

- battery cycle count;
- battery health / maximum capacity;
- Activation Lock / Find My state;
- MDM / Remote Management state.

These fields affect used-device confidence but cannot make an ambiguous hardware configuration exact.

### Price and landed-cost path

Resolved configuration travels in `Listing.configuration` through normal price-history matching. Current listing price, shipping and currency therefore stay attached to the observed exact configuration. Existing sourced CAD FX and landed-cost logic then calculate Canadian landed cost without inventing a static Apple price.

## Manufacturer support API ingestion

Motherboard enrichment discovers ranked same-manufacturer CPU-support endpoints and can asynchronously ingest JSON/API or HTML support matrices.

### Completeness rules

A CPU matrix is complete only with explicit pagination proof:

- last page according to an explicit total-page count;
- fetched range reaches an explicit total-row count; or
- API explicitly reports no more pages/rows.

If an explicit total row count does not match the final deduplicated matrix, completeness is revoked.

Plain HTML, a short page, an empty next link, or a response smaller than the requested page size are not completeness proofs.

### Evidence ordering

Static manufacturer HTML remains useful evidence. API ingestion follows these rules:

- a complete API matrix can replace static rows and promote matrix completeness;
- a larger partial API matrix may replace a smaller static matrix but remains incomplete;
- a smaller partial response cannot erase stronger static coverage.

All support API requests stay on the verified manufacturer host and pagination is bounded.

## Still unresolved

This implementation does not yet claim:

- discovery of manufacturer APIs that are not linked from the verified product/support surface;
- authoritative Apple order-number mappings for every historical generation, country or build-to-order option;
- warranty/AppleCare status from external account/service data;
- shipped motherboard BIOS or hardware revision unless manufacturer/seller evidence explicitly provides it.
