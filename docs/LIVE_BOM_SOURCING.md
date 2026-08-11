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
      ├── manufacturer / MPN when source provides it
      ├── native price
      ├── shipping
      ├── availability
      └── seller/source confidence
      │
      ▼
compatibility text filters
      │
      ▼
automatic exact-SKU manufacturer enrichment
      │
      ├── curated association first
      ├── cached verified manufacturer association
      ├── official manufacturer search/sitemap discovery
      └── field-level compatibility provenance
      │
      ▼
Bank of Canada FX + Canadian landed cost
      │
      ▼
compatible complete-build solver
      │
      ▼
selected current BOM / TCO evidence
```

## Files

- `data/market/bom-sourcing.json` — component queries, matching rules, source list and selection policy.
- `data/market/bom-current.json` — current candidates and selected products for each component.
- `data/market/bom-price-history.json` — append-only observations of landed CAD cost.
- `data/market/manufacturer-discovery.json` — official manufacturer names/domains and bounded automatic association policy.
- `data/market/manufacturer-associations.json` — cached verified/not-verified automatic manufacturer product-page associations.
- `data/market/spec-enrichment.json` — curated exact-SKU associations plus automatic-discovery policy.
- `data/market/spec-evidence.json` — latest field-level manufacturer specification evidence admitted into compatibility solving.
- `src/lowpower_llm_cluster/bom_sourcing.py` — discovery, filtering, landed-cost ranking and complete-build orchestration.
- `src/lowpower_llm_cluster/manufacturer_discovery.py` — automatic official product-page association discovery/cache.
- `src/lowpower_llm_cluster/spec_enrichment.py` — curated and automatic compatibility-field extraction.

## Commands

```bash
llm-cluster-refresh refresh-bom
llm-cluster-refresh bom-config
llm-cluster-refresh spec-config
llm-cluster-refresh spec-evidence
llm-cluster-refresh manufacturer-config
llm-cluster-refresh manufacturer-associations
llm-cluster-refresh compatible-builds
llm-cluster-refresh tco --scenario mixed-3yr --ownership new-build
```

The normal autonomous refresh runs Bank of Canada FX first, then refreshes the BOM, enriches exact manufacturer specifications, rebuilds compatible complete-node combinations, and then generates TCO and recommendation reports. This ordering means distributor prices use the newest sourced FX and compatibility decisions use the newest verified manufacturer facts.

## Selection policy

A candidate must pass the component's positive/negative text filters and minimum seller confidence. Current landed CAD cost is calculated from item price, shipping, FX and configured tax assumptions.

The selector generally favors the strongest combination of:

1. compatibility filter match;
2. seller/source confidence;
3. landed CAD price.

An authorized distributor may be preferred over a marketplace seller when its landed cost is within the configured percentage tolerance. This is intentional: the cheapest listing is not automatically the best procurement choice.

## Manufacturer/MPN identity

Mouser, DigiKey and manufacturer JSON-LD adapters preserve manufacturer and manufacturer part number in the normalized listing whenever the upstream source provides them. That identity is intentionally separate from seller identity.

When a live candidate has a trustworthy manufacturer + MPN but no curated spec mapping, automatic association discovery may locate an official manufacturer product page. It only searches configured manufacturer-owned domains, verifies MPN/model identity on the candidate page, and caches the result before generic compatibility extraction is allowed.

Marketplace listings without a trustworthy board/product MPN generally remain provisional for exact physical compatibility.

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

Credential-disabled sources are skipped rather than fabricated. Automatic manufacturer page discovery does not require a search-engine API key because it is bounded to manufacturer-owned URLs/search pages/sitemaps from the configured registry.

## Guardrails

- Do not treat a search result as compatible solely because it is cheap.
- Keep exact listing URL, seller, observation time and confidence with every sourced cost.
- Keep manufacturer + MPN identity separate from seller/source identity.
- Only configured official manufacturer domains can become automatic authoritative spec associations.
- Cache failures/ambiguity as not verified rather than forcing a match.
- Preserve native price/currency in history; landed CAD is a derived snapshot.
- Never silently replace a failed live source with a fake current price.
- Planning fallbacks remain visible until a valid sourced candidate replaces them.
- Ownership-aware TCO still removes already-owned components from incremental acquisition even when a sourced market reference exists for their avoided replacement cost.
