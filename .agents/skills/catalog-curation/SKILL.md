# Catalog Curation Skill

Use for the project's primary workflow: discovering, adding, correcting or refreshing products.

1. Read the charter, guardrails, `specs/HARDWARE_CATALOG.md`, `specs/EVIDENCE.md` and `docs/CONCURRENCY.md`.
2. `data/parts.json` is the canonical manifest; reviewed records live under `data/catalog/*.json`.
3. Discovery observations/history are staging evidence, not automatic canonical truth.
4. Prefer the bounded async discovery/service pipeline for current sources. Keep blocking network/filesystem/SQLite/meaningful parse work off the event loop.
5. Preserve bounded queues and worker limits. Do not replace streaming batches with catalog-sized task fan-out or full-refresh materialization.
6. Reuse HTTP/DNS/cache/SQLite resources in long-running service mode; use conditional GET validators whenever parsed observations are safely cacheable.
7. Honor `Retry-After`, retry transient errors with bounded backoff, and let adaptive source concurrency back off faster than it recovers.
8. Do not mark listings disappeared when their source failed or was rate-limited for the refresh.
9. Preserve exact configuration, verification date, price/source URL and listing status.
10. Record source/seller/SKU confidence when the evidence supports it; never substitute seller confidence for exact-SKU confidence.
11. Distinguish included/fixed RAM from board-verified maximum and CPU theoretical maximum. Add board memory source URL/date when available.
12. Preserve dimensions, DC input, PSU/cooling and host requirements when those affect deployment.
13. Unknown performance is valid. Never fill missing throughput with TOPS-based arithmetic.
14. When real vendor/community/local performance exists, preserve model/runtime/workload/quantization/context provenance. Multi-source ranges require compatible independent measured sources.
15. Keep specialist vision/audio metrics separate from LLM throughput.
16. Keep sold-out/EOL references when technically useful, but mark lifecycle/availability accurately and track used-market price history separately.
17. Profile before adding process pools or other high-overhead parallelism; optimize the measured bottleneck.
18. Regenerate `PARTS.md` after canonical catalog changes and run catalog/governance/async-blocking/tests.
19. Update README, CHANGELOG, TODO and relevant specs whenever behavior changes.
