# Dashboard UX and Information Architecture

The catalog dashboard is a **research console**, not a raw-data dump. Its job is to help a person move from “what is in this catalog?” to “which few products should I inspect?” without hiding evidence boundaries.

## Running dashboard

The dashboard supports both a persistent live web service and standalone static generation.

```bash
# Persistent live service. Port 8788 avoids the discovery health endpoint on 8787.
llm-cluster-dashboard --host 127.0.0.1 --port 8788

# Preserve a standalone static artifact when needed.
llm-cluster dashboard --output results/catalog-dashboard.html
```

The persistent service serves `/` and `/index.html`, exposes `/healthz`, and watches `results/catalog-history.sqlite3` directly. The browser receives live database and service activity through Server-Sent Events, so committed discovery batches become visible in the activity state without waiting for a complete scan cycle.

A static catalog snapshot is still written to `results/catalog-dashboard.html`. Periodic static regeneration is optional through `--refresh-interval`; it is not required for live logs or live database counters.

### Live logs

`/logs` is a dedicated live event-log page. It shows current observation/listing/run counters plus service and database events as they occur. Supporting APIs are:

- `/api/state` — current SQLite observation/listing/run state;
- `/api/logs` — recent JSONL event history;
- `/api/events` — Server-Sent Events stream;
- `/healthz` — dashboard/database health.

The main dashboard includes a persistent LIVE indicator and direct link to the Logs page. Discovery service events and dashboard-observed database changes share `results/events.jsonl` by default.

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

The live operational layer deliberately keeps staging/runtime state visually distinct from canonical catalog truth. Future work can extend that separation with:

- source-level queue/concurrency charts;
- price-history timelines from `CatalogHistory`;
- saved/exportable filter and comparison sets;
- model-fit and landed-cost actions from the selected product;
- distributed worker/cycle status from the coordinator;
- optional performance evidence/range charts when real compatible records exist.
