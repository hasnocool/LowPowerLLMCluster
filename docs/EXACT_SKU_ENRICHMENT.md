# Exact-SKU Specification Enrichment

Live market listings are useful for price and availability, but listing titles are not authoritative enough to prove physical or electrical compatibility. This layer now combines curated exact-SKU mappings with automatic manufacturer association discovery, extracts compatibility facts, records field-level provenance, and then re-runs the complete-build solver.

## Pipeline

```text
live listing
  -> preserve manufacturer + MPN/SKU from structured source
  -> curated exact association if one exists
  -> otherwise automatic manufacturer discovery
       -> official manufacturer registry
       -> cached verified association
       -> official search-page candidates when configured
       -> official robots.txt / sitemap candidates
       -> manufacturer-domain-only candidate pages
       -> MPN/model identity scoring
       -> cache verified association
  -> fetch verified HTTPS manufacturer product page
  -> curated field extraction OR conservative generic parser
  -> field-level provenance
  -> merge over weaker title-derived facts
  -> compatibility solver
```

The enrichment pass runs inside `llm-cluster-refresh refresh-bom` after online BOM discovery and before complete-build solving.

## Automatic association discovery

`data/market/manufacturer-discovery.json` is a manufacturer-level registry, not a product mapping. It records canonical manufacturer names, aliases and official domains. It may also contain manufacturer-owned search URL templates when a stable search endpoint is known.

The automatic discovery engine is in `src/lowpower_llm_cluster/manufacturer_discovery.py`. It uses the listing's manufacturer plus MPN/SKU and deliberately avoids treating arbitrary search-engine or retailer pages as authoritative product associations.

Discovery order is:

1. reuse an unexpired verified association from `data/market/manufacturer-associations.json`;
2. use an explicit manufacturer URL hint when a structured source provides one;
3. inspect configured search pages on the official manufacturer domain;
4. inspect bounded official sitemaps discovered from `robots.txt` or `/sitemap.xml`;
5. fetch a small candidate set and verify manufacturer/MPN/model identity on-page;
6. cache the association only when its identity score clears the configured conservative threshold.

The default policy requires an MPN/SKU, limits sitemap and URL scanning, caches verified associations for 30 days, and requires an identity score of at least 0.72. Failed or ambiguous discovery is cached as `not_verified` rather than promoted to exact evidence.

## Structured source identity

Mouser and DigiKey adapters retain manufacturer name and manufacturer part number in each listing's `configuration` object. Manufacturer JSON-LD listings preserve brand/manufacturer plus MPN as well. This identity survives into BOM candidates and gives automatic discovery something stronger than a marketplace title to work with.

Marketplace listings without a trustworthy MPN generally remain unassociated; this is intentional.

## Automatic field extraction

Automatically associated pages use a conservative generic parser for compatibility-relevant facts. Current extraction targets include:

- CPU socket, DDR generations, PCIe generation and processor/base-power fields;
- motherboard socket, DDR generation, PCIe x16/gen/lanes, M.2 support, form factor and lane-sharing statements;
- PSU wattage, ATX generation, 12V-2x6/12VHPWR and PCIe 8-pin capability;
- chassis GPU clearance, CPU-cooler clearance, PSU clearance, form-factor support and expansion-slot count;
- cooler height and supported CPU sockets;
- exact GPU length, slot width, recommended/minimum PSU, power connectors, PCIe generation/lanes and Resizable BAR requirement when the page states them.

The parser does not fabricate values for fields it cannot recognize. Curated product associations remain available for manufacturer pages whose structure or wording needs product-specific handling.

## Evidence policy

Manufacturer enrichment is deliberately conservative:

- only HTTPS manufacturer-domain pages can become automatic authoritative associations;
- a verified manufacturer + MPN/model identity is required before automatically parsed fields are admitted;
- curated exact SKU matches outrank title-only model matches and automatic discovery;
- each promoted field keeps source URL, observation time, extraction method, association ID, identity score and confidence;
- fields not supported by the associated source remain unknown;
- manufacturer evidence may override weaker title-derived facts field by field;
- a GPU family name never inherits board-partner dimensions automatically;
- cached associations expire and must be reverified periodically.

`data/market/spec-enrichment.json` stores curated associations and policy. `data/market/manufacturer-discovery.json` stores manufacturer-domain discovery policy. `data/market/manufacturer-associations.json` stores verified automatic associations. `data/market/spec-evidence.json` stores the latest field-level evidence generated during refresh.

## Initial curated products

The curated rules intentionally remain for models where official specification pages provide useful constraints or require product-specific interpretation:

- MSI B550-A PRO;
- MSI PRO B660M-A DDR4;
- Corsair RM750e `CP-9020295-NA`;
- Corsair 4000D Airflow `CC-9011200-WW`;
- Intel Core i5-12400;
- NVIDIA GeForce RTX 3090 Founders Edition;
- Intel Arc B580 Limited Edition.

Automatic discovery expands coverage beyond this list as new exact-MPN distributor products enter the live BOM candidate pool.

## Compatibility outcomes

A manufacturer-enriched field can change a build in either direction:

- **promote** `provisionally_compatible` to `compatible` when the missing constraint is proven;
- **leave provisional** when other required facts remain unresolved;
- **reject** a previously plausible build when the verified dimension, connector, lane or power fact exposes a conflict.

This is intentional. Enrichment is an evidence layer, not a mechanism for making more builds pass.

## GPU rule

Reference GPU specifications are not copied onto arbitrary add-in-board partner cards. A listing must identify the reference/Founders/Limited Edition board or expose a board-partner MPN that can be associated with an official board-partner product page before physical dimensions and connectors can be considered exact.

## CLI

```bash
llm-cluster-refresh refresh-bom
llm-cluster-refresh spec-config
llm-cluster-refresh spec-evidence
llm-cluster-refresh manufacturer-config
llm-cluster-refresh manufacturer-associations
llm-cluster-refresh compatible-builds
```

`manufacturer-config` shows the official manufacturer registry and discovery limits. `manufacturer-associations` shows cached verified/not-verified automatic associations. `spec-evidence` shows the field-level evidence actually admitted into the compatibility layer.

## Extending coverage

For a new manufacturer, prefer adding only its canonical name, aliases and official domain to `manufacturer-discovery.json`. Automatic MPN discovery can then grow exact-product coverage as listings appear.

Use a curated `spec-enrichment.json` association only when automatic discovery cannot reliably find the product page or the manufacturer page needs product-specific extraction rules.

Do not use retailer prose, third-party search results, sibling products or same-chip assumptions as exact manufacturer specification evidence.
