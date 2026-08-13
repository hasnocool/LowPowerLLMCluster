# Dashboard UX and Information Architecture

The catalog dashboard is a **research console**, not a raw-data dump. Its job is to help a person move from “what is in this catalog?” to “which few products should I inspect?” without hiding evidence boundaries.

## Running dashboard

The dashboard supports both static generation and a persistent web service.

```bash
# Persistent service; refreshes the generated HTML snapshot every 60 seconds.
llm-cluster-dashboard --host 127.0.0.1 --port 8787

# Preserve a standalone static artifact when needed.
llm-cluster dashboard --output results/catalog-dashboard.html
```

The persistent service serves `/` and `/index.html`, exposes `/healthz`, and keeps `results/catalog-dashboard.html` current. A refresh failure does not discard the last known-good HTML snapshot, so a temporary catalog/render problem does not unnecessarily take down the dashboard.

## Design rule

```text
UNDERSTAND  →  BROWSE  →  INSPECT  →  COMPARE
 overview      shortlist    one item     few items
```

The dashboard should not make every catalog field a permanent column. Decision-critical fields stay visible in Browse; detailed deployment, evidence and provenance fields live in the product inspector; cross-product evaluation belongs in Compare.

## Overview

Overview answers four questions before the user starts filtering:

1. How many catalog records and LLM candidates exist?
2. How much decision-critical data is actually known?
3. Which entries currently rank highest as research candidates?
4. What kinds of hardware make up the catalog?

Coverage is shown separately for price, memory, power boundaries, SKU confidence and performance evidence. Missing data is not silently converted to zero.

## Browse

Browse keeps the default table intentionally narrow:

- product + vendor / class;
- midpoint/range price and price status;
- verified or board-supported memory and its basis;
- published power boundary and scope;
- risk;
- performance-evidence source class;
- catalog/research score;
- comparison selection.

Search spans product, vendor, hardware class, accelerator/software and workload text. Advanced filters live in a dedicated panel and collapse on small screens.

The score is always a **shopping/research heuristic**. It is never presented as predicted tokens/sec or a benchmark result.

## Product inspector

Selecting a row opens an off-canvas inspector organized by meaning rather than schema order:

- Why it is here
- Buying snapshot
- Memory and capacity evidence
- Power and deployment
- Software and workload
- Evidence and provenance

External links are limited to HTTP/HTTPS URLs and catalog text is escaped before insertion into rendered HTML.

## Compare

Compare supports up to four products at once. It uses a matrix with stable rows for price, score, memory/evidence, power/scope, risk, lifecycle, SKU confidence, LLM/software support, form factor, DC input, host requirements and performance evidence.

Comparison state and filters are stored locally in the browser. The generated dashboard remains self-contained and has no external JS/CSS dependency.

## Responsive behavior

Desktop uses a persistent navigation rail and filter column. Tablet collapses the navigation labels. Mobile moves navigation to the bottom and turns filters into an overlay. Product detail stays in a drawer rather than forcing horizontal table expansion.

## Next data-UX layer

The rebuilt catalog dashboard is still generated from canonical catalog data. The next dashboard phase should add **live/staging operational views** without mixing them into canonical truth:

- discovery run/source health from `llm-cluster-service`;
- current staging observations and change events;
- price-history timelines from `CatalogHistory`;
- saved/exportable filter and comparison sets;
- model-fit and landed-cost actions from the selected product;
- distributed worker/cycle status from the coordinator;
- optional performance evidence/range charts when real compatible records exist.

Those views must clearly distinguish canonical catalog records, staging discovery observations, runtime telemetry and measured performance evidence.
