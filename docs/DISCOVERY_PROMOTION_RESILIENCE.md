# Discovery & Canonical Promotion Resilience

This document describes the runtime added after analysis of long-running discovery/debug data where observation volume grew rapidly while canonical promotion lagged and repeatedly failing sources dominated cycle time.

## Pipeline

```text
discovery
  -> normalized identity
  -> official-source manufacturer enrichment
  -> bounded held-record structured re-fetch
  -> promotion evidence gates
  -> canonical auto-promoted fragment
```

The system improves evidence before lowering any canonical threshold. Announcement-only records, generic metadata fallbacks, missing manufacturer identity, weak source confidence, non-HTTPS product URLs, and out-of-stock listings remain held until the required evidence improves.

## Promotion watchdog

Every successful local discovery cycle running through `llm-cluster-service` uses `PromotionCatalogRefreshEngine`. It writes:

- `results/promotion-latest.json` — promotion decisions, hold reasons and per-source promotion yield;
- `results/promotion-enrichment-latest.json` — bounded structured enrichment attempts and results;
- `results/promotion-health.json` — engine identity, run id, promotion completion time and freshness;
- `data/catalog/auto-promoted.json` — canonical records that passed the gates.

The debug event stream emits `promotion_engine_started`, `canonical_promotion_complete`, or `canonical_promotion_failed`. The dashboard `/healthz` endpoint reports degraded status when the newest completed discovery run is newer than the last successful promotion pass.

## Source cooldown

Quality learning now applies to curated and learned sources. A persistent `source_cooldown` table classifies repeated failures and prevents known-bad sources from consuming every cycle:

- access denied / persistent 403: long bounded cooldown;
- HTTP 429: medium exponential cooldown;
- TLS certificate failure: long bounded cooldown without disabling TLS verification;
- connection/DNS failure: exponential cooldown;
- 5xx: shorter retry cadence;
- protocol/header failures: bounded cooldown.

Sources are never permanently blacklisted. A later probe can succeed and reset the failure streak.

## HTTP header compatibility

The service uses a bounded 64 KiB HTTP line/header-field parser (hard-capped at 128 KiB) to support legitimate manufacturer/CDN responses that exceed aiohttp's normal 8 KiB field limit. TLS verification remains enabled and response bodies remain bounded separately.

## Observation history compaction

`listing_state` is updated every cycle, but unchanged observations are persisted at most once per hour by default. New listings, semantic changes, disappearance/reappearance events, and hourly heartbeats remain in history. This prevents high-frequency fixtures and stable listings from creating tens of thousands of redundant observation rows.

## Manufacturer and product identity

Official source names and manufacturer-owned domains can supply manufacturer identity with explicit evidence. A stable HTTPS product-detail URL on a known official manufacturer source can satisfy product identity when an MPN/SKU is not published. Generic category/search pages cannot use this fallback.

## Held-record enrichment

A bounded number of held official product URLs are re-fetched per cycle and parsed specifically for schema.org `Product` metadata. Successful structured enrichment can add manufacturer, SKU/MPN/model data and clear metadata-fallback status before the record is re-evaluated for promotion.

## Promotion review

The dashboard `/discoveries` page and `/api/promotion-state` project the complete active listing population into:

- `discovered`
- `held`
- `promotion_ready`
- `canonical`

Promotion decisions are persisted by normalized listing identity, so adaptive source skips do not erase a record's last known status. Canonical state is tied to exact promotion provenance rather than only manufacturer/SKU identity.

Additional endpoints:

- `/api/source-health` — source quality, success/duplicate rates, failure class/cooldown and promotion yield;
- `/api/promotion-health` — current promotion watchdog state;
- `/healthz` — overall dashboard + promotion freshness health.

The terminal equivalent is `llm-cluster-promotion-state`.

## Deployment

After updating a checkout, reinstall the editable package so the console-script entrypoints reflect the current code:

```bash
python -m pip install -e .
llm-cluster-install-service --config config/discovery.local.json --with-dashboard --enable-now
```

The installer passes the scanner history, discovery output and promotion artifact paths to the dashboard unit so custom deployments do not silently fall back to repository-relative defaults.
