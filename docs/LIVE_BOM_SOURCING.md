# Live BOM Sourcing

The TCO engine can replace generic component assumptions with current online product listings one BOM line at a time.

## Pipeline

```text
component requirement
      │
      ├── CPU/host
      ├── motherboard
      ├── RAM
      ├── storage
      ├── PSU
      ├── PCIe/OCuLink/riser
      ├── cooling
      └── chassis
      │
      ▼
component-specific search queries
      │
      ├── Mouser API
      ├── DigiKey Product Information API
      └── eBay Browse API (Canada)
      │
      ▼
normalize Listing
      │
      ├── title / SKU / seller
      ├── native price
      ├── shipping
      ├── availability
      └── seller/source confidence
      │
      ▼
compatibility text filters
      │
      ▼
Bank of Canada FX + Canadian landed cost
      │
      ▼
rank candidate products
      │
      ▼
selected current BOM component
      │
      ▼
TCO sourced cost override
```

## Files

- `data/market/bom-sourcing.json` — component queries, matching rules, source list and selection policy.
- `data/market/bom-current.json` — current candidates and selected products for each component.
- `data/market/bom-price-history.json` — append-only observations of landed CAD cost.
- `src/lowpower_llm_cluster/bom_sourcing.py` — discovery, filtering, landed-cost ranking and selection.

## Commands

```bash
llm-cluster-refresh refresh-bom
llm-cluster-refresh bom-config
llm-cluster-refresh tco --scenario mixed-3yr --ownership new-build
```

The normal autonomous refresh runs Bank of Canada FX first, then refreshes the BOM, then generates TCO and recommendation reports. This ordering means USD/EUR distributor prices can be converted with the newest sourced FX snapshot before selection.

## Selection policy

A candidate must pass the component's positive/negative text filters and minimum seller confidence. Current landed CAD cost is calculated from item price, shipping, FX and configured tax assumptions.

The selector generally favors the strongest combination of:

1. compatibility filter match;
2. seller/source confidence;
3. landed CAD price.

An authorized distributor may be preferred over a marketplace seller when its landed cost is within the configured percentage tolerance. This is intentional: the cheapest listing is not automatically the best procurement choice.

## TCO integration

`load_tco_scenarios()` overlays selected live component costs onto the fallback planning assumptions. Every infrastructure line keeps its basis:

- `sourced_live_listing_landed_cad` — current selected product listing;
- `planning_assumption` — no usable current product was selected;
- `already_owned` — compatible component is reused under the ownership profile;
- `missing_cost` — neither sourced nor fallback cost exists.

This allows a single GPU-node TCO to contain a mixture such as a sourced PSU, sourced SSD and marketplace chassis while still using a clearly labeled fallback for a motherboard if discovery failed.

## Credentials

The repository never stores source credentials. Configure supported APIs through environment/GitHub secrets already used by market discovery:

- `MOUSER_API_KEY`
- `DIGIKEY_CLIENT_ID`
- `DIGIKEY_ACCESS_TOKEN`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`

Credential-disabled sources are skipped rather than fabricated.

## Guardrails

- Do not treat a search result as compatible solely because it is cheap.
- Keep exact listing URL, seller, observation time and confidence with every sourced cost.
- Preserve native price/currency in history; landed CAD is a derived snapshot.
- Never silently replace a failed live source with a fake current price.
- Planning fallbacks remain visible until a valid sourced candidate replaces them.
- Ownership-aware TCO still removes already-owned components from incremental acquisition even when a sourced market reference exists for their avoided replacement cost.
