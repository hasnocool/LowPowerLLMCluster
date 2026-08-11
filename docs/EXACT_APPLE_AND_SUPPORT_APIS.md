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

`exact_configuration=true` requires identity + chip + RAM + storage and no conflicting pre-existing evidence. A-number alone does not define RAM, storage or GPU bin. GPU core count is never inferred from an M-series family name.

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
- authoritative Apple order-number mappings for every generation/region;
- warranty/AppleCare status from external account/service data;
- shipped motherboard BIOS or hardware revision unless manufacturer/seller evidence explicitly provides it.
