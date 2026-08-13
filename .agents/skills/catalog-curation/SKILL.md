# Catalog Curation Skill

Use for the project's primary workflow: discovering, adding, correcting or refreshing products.

1. Read the charter, guardrails, `specs/HARDWARE_CATALOG.md`, `specs/EVIDENCE.md`, `docs/CONCURRENCY.md` and—when distributed execution is involved—`docs/DISTRIBUTED_RUNTIME.md`.
2. `data/parts.json` is the canonical manifest; reviewed records live under `data/catalog/*.json`.
3. Local/remote discovery observations and history are staging evidence, not automatic canonical truth.
4. Prefer the bounded async discovery/service pipeline. Keep blocking network/filesystem/SQLite/meaningful parse work off the event loop.
5. Preserve bounded queues and worker limits. Do not replace streaming batches with catalog-sized task fan-out or full-refresh materialization.
6. Reuse HTTP/DNS/cache/SQLite resources in long-running service/worker modes; conditional validators are preferred when parsed observations are safely cacheable.
7. Cache state must remain bounded by TTL/entry pruning. Compression may reduce persistent footprint but does not replace lifecycle bounds.
8. Honor `Retry-After`, retry transient errors with bounded backoff, let adaptive source concurrency back off faster than it recovers, and let repeated source failures trip the circuit breaker.
9. Adaptive batch sizing may change transaction/batch size but must never change observation identity or evidence semantics.
10. Use `streaming_json` for exceptionally large JSON arrays instead of fully decoding them first.
11. Use process-isolated adapters only for parsers that genuinely need isolation; keep commands explicit and shell-free.
12. A failed/rate-limited local or remote source must not mark its listings disappeared for that cycle.
13. Distributed workers may discover/parse source data but must not independently write canonical catalog/history/promotion state.
14. Preserve remote lease/heartbeat/idempotent-batch semantics; retries must never duplicate accepted observations merely because a worker restarted.
15. Preserve exact configuration, verification date, price/source URL and listing status.
16. Record source/seller/SKU confidence when supported; never substitute seller confidence for exact-SKU confidence.
17. Distinguish included/fixed RAM from board-verified maximum and CPU theoretical maximum. Add board memory source URL/date when available.
18. Preserve dimensions, DC input, PSU/cooling and host requirements when they affect deployment.
19. Unknown performance is valid. Never fill missing throughput with TOPS-based arithmetic.
20. Real vendor/community/local performance must preserve model/runtime/workload/quantization/context provenance; multi-source ranges require compatible independent sources.
21. Keep specialist vision/audio metrics separate from LLM throughput.
22. Keep sold-out/EOL references when technically useful, with lifecycle/availability labels and separate used-market history.
23. Regenerate `PARTS.md` after canonical catalog changes and run governance/async-blocking/catalog/tests; material runtime changes also run the synthetic perf gate.
24. Update README, CHANGELOG, TODO and relevant specs whenever behavior or the next-work sequence changes.
