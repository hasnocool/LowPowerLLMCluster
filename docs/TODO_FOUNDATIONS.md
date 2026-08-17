# Finite TODO foundations

This document describes the finite market-intelligence capabilities completed while leaving continuous evidence-harvesting and catalog-expansion goals open.

## Owned-host compatibility

`lowpower_llm_cluster.owned_host.validate_owned_host()` validates an accelerator against already-owned host facts without silently purchasing replacement parts or assuming missing compatibility data.

The validator checks:

- physical PCIe slot width;
- explicitly required PCIe generation and wired lane count;
- whether a candidate slot is available;
- PSU manufacturer/planning wattage requirements;
- caller-supplied complete-system peak estimate plus configurable PSU headroom;
- multiplicity of GPU power connectors;
- chassis GPU length and slot-width clearance; and
- caller-supplied GPU cooling capacity against accelerator-board power evidence.

Missing facts remain `provisionally_compatible`. Accelerator TGP/TBP is used only for the accelerator cooling check and is never relabeled as complete-node wall-input power.

CLI example:

```bash
lowpower-llm-market owned-host gpu.json owned-host.json --exact-gpu-facts exact-board.json
```

## Historical landed-CAD evidence

`lowpower_llm_cluster.landed_history` stores append-only landed-cost snapshots containing the native listing price, shipping, brokerage, province planning preset, exact FX snapshot, and optional tariff evidence used at observation time.

Province presets are planning defaults, not tax or customs guarantees. A tariff assumption is accepted only with an explicit HS code, duty rate, verification date, and HTTPS evidence URL. Customs treatment can vary with origin, classification, seller terms, courier handling, exemptions, and current law.

Historical snapshots are not recomputed at today's FX rate. `fx_only_delta()` permits a pure-FX comparison only when all non-FX acquisition assumptions are unchanged.

CLI examples:

```bash
lowpower-llm-market landed-snapshot listing.json --province BC
lowpower-llm-market landed-snapshot listing.json --province ON --tariff-evidence tariff.json
lowpower-llm-market landed-history --source ebay-ca --source-id ITEM_ID
```

A tariff evidence file has the following shape:

```json
{
  "hs_code": "8471.50",
  "duty_rate": 0.0,
  "source_url": "https://example.invalid/official-tariff-evidence",
  "verified_on": "2026-08-17",
  "origin_country": "US",
  "description": "Exact planning evidence for this classification"
}
```

The example URL is intentionally non-operational. Real records must use an auditable HTTPS source.

## Provider quota observations

Structured online adapters now inspect provider response headers for explicit remaining-quota, limit, reset timestamp, and reset-after metadata. Recognized observations are persisted to `data/market/provider-quotas.json` with a restart-safe latest view plus bounded history.

No quota value is invented when the provider does not expose one. Ambiguous numeric reset values are retained as raw evidence rather than guessed into a timestamp.

## Notification delivery

Generated alert evidence can be delivered through:

- generic HTTPS JSON webhooks;
- text-first HTTPS chat webhooks; and
- SMTP email.

Webhook delivery uses asynchronous `httpx`. SMTP is synchronous in the Python standard library, so the complete SMTP operation is isolated with `asyncio.to_thread()` and cannot block the event loop. Multiple adapter deliveries are fanned out concurrently, and one failed adapter does not prevent other adapters from running.

`data/market/notifications.json` contains disabled examples. Credentials, passwords, and webhook URLs are supplied through environment variables rather than committed to the repository.

```bash
lowpower-llm-market notify --maximum-priority P2
```

## Used-hardware condition evidence

When structured marketplace APIs expose the fields, the catalog pipeline now preserves explicit:

- marketplace condition and condition ID;
- return terms;
- AppleCare/warranty statements;
- GPU fan/cooler condition statements; and
- existing seller reputation/history evidence.

Free-text condition parsing is deliberately narrow. Absence of a statement stays unknown and never becomes an inferred positive condition.

## Previously implemented TODO capabilities

The TODO audit also confirmed that several unchecked entries were already implemented in the existing codebase:

- confidence-aware performance ranges require multiple independent compatible measured sources;
- model-family capacity presets extend beyond the default Q4 screen;
- third-party benchmark importers exist for mapped JSON/JSONL records;
- specialist vision/audio measurements remain separate from LLM throughput;
- form factor, dimensions, DC input, PSU/cooling and host requirements are normalized without inventing fields;
- board-level RAM limits are preserved separately from CPU theoretical memory limits; and
- factory/shipped BIOS resolution only occurs through explicit manufacturer-published mappings, while seller firmware evidence remains lower authority.

## Intentionally still open

Continuous harvesting and market expansion remain open-ended by design. Examples include collecting additional exact power measurements, expanding hardware/vendor coverage, adding newly available legal structured market sources, maintaining runtime benchmark adapters, and adding new manufacturer mappings only when verifiable evidence appears.

A framework being available is not sufficient reason to mark those continuous evidence-population goals complete.
