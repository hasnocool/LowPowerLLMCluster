# Exact-SKU Specification Enrichment

Live market listings are useful for price and availability, but listing titles are not authoritative enough to prove physical or electrical compatibility. This layer associates sufficiently specific listings with manufacturer specification pages, extracts compatibility facts, records field-level provenance, and then re-runs the complete-build solver.

## Pipeline

```text
live listing
  -> exact SKU / distinctive model association
  -> HTTPS manufacturer specification page
  -> identity verification terms
  -> field extraction
  -> field-level provenance
  -> merge over title-derived facts
  -> compatibility solver
```

The enrichment pass runs inside `llm-cluster-refresh refresh-bom` after online BOM discovery and before complete-build solving.

## Evidence policy

Manufacturer enrichment is deliberately conservative:

- a manufacturer page must be fetched successfully;
- configured identity terms must occur on the page before any configured field is admitted;
- exact SKU matches outrank title-only model matches;
- each promoted field keeps source URL, observation time, extraction method, association ID and confidence;
- fields not supported by the associated source remain unknown;
- manufacturer evidence may override weaker title-derived facts field by field;
- a GPU family name never inherits board-partner dimensions automatically.

`data/market/spec-enrichment.json` stores associations and extraction rules. `data/market/spec-evidence.json` stores the latest field-level evidence generated during refresh.

## Initial enrichable products

The initial rules intentionally target a small set of models for which official specification pages provide useful constraints:

- MSI B550-A PRO: AM4, DDR4, PCIe layout, M.2 support, form factor and secondary-slot sharing note;
- MSI PRO B660M-A DDR4: LGA1700, DDR4, PCIe layout, M.2 support and mATX form factor;
- Corsair RM750e `CP-9020295-NA`: 750 W, ATX 3.1, native 12V-2x6 and PCIe power capability;
- Corsair 4000D Airflow `CC-9011200-WW`: motherboard support, 360 mm GPU clearance, 170 mm CPU-cooler clearance and PSU length;
- Intel Core i5-12400: LGA1700 and DDR4/DDR5 CPU compatibility facts;
- NVIDIA GeForce RTX 3090 Founders Edition: exact reference-board dimensions, slot width, PSU and connector requirements;
- Intel Arc B580 Limited Edition: exact board dimensions, PSU/connector requirement and Resizable BAR requirement.

Broad partner-card listings remain provisional until a board-specific association exists.

## Compatibility outcomes

A manufacturer-enriched field can change a build in either direction:

- **promote** `provisionally_compatible` to `compatible` when the missing constraint is proven;
- **leave provisional** when other required facts remain unresolved;
- **reject** a previously plausible build when the verified dimension, connector, lane or power fact exposes a conflict.

This is intentional. Enrichment is an evidence layer, not a mechanism for making more builds pass.

## GPU rule

Reference GPU specifications are not copied onto arbitrary add-in-board partner cards. A listing must specifically identify the reference/Founders/Limited Edition board, or later match an exact board-partner SKU association, before its board dimensions and connectors can be considered exact.

## CLI

```bash
llm-cluster-refresh refresh-bom
llm-cluster-refresh spec-config
llm-cluster-refresh spec-evidence
llm-cluster-refresh compatible-builds
```

`compatible-builds` reports how many manufacturer-spec fields support the selected build and still lists unresolved compatibility facts.

## Extending coverage

To add an exact product:

1. identify a stable HTTPS manufacturer specification page;
2. add an association with exact SKU when available and distinctive model terms as fallback;
3. add identity-verification terms that make accidental cross-model association unlikely;
4. add only compatibility fields the manufacturer page actually supports;
5. add a deterministic test when the new field changes solver behavior.

Do not use retailer prose, search snippets, sibling products or same-chip assumptions as exact manufacturer specification evidence.
