# Catalog Curation Skill

Use for discovering, adding, correcting or refreshing products.

1. Read the charter, guardrails, `specs/HARDWARE_CATALOG.md`, `specs/EVIDENCE.md`, `docs/CONCURRENCY.md` and—when distributed execution is involved—`docs/DISTRIBUTED_RUNTIME.md` + `docs/DISTRIBUTED_SECURITY.md`.
2. `data/parts.json` is the canonical manifest; reviewed records live under `data/catalog/*.json`.
3. Local/remote discovery observations, content-addressed source snapshots and history are staging evidence, not automatic canonical truth.
4. Prefer the bounded async discovery/service pipeline. Keep blocking network/filesystem/SQLite/meaningful parse work off the event loop.
5. Preserve bounded queues/workers and streamed batches. Do not replace them with catalog/cycle-sized task fan-out or full-result materialization.
6. Reuse HTTP/DNS/cache/SQLite/client resources in long-running service/worker modes.
7. Cache/snapshot state remains bounded/freshness-aware. Immutable CAS snapshots may be shared, but replay is explicit and stale snapshots never masquerade as live source truth.
8. Honor `Retry-After`, bounded retries, adaptive concurrency and source circuit breakers.
9. Adaptive batch sizing changes resource control only; it must not alter observation identity/evidence semantics.
10. Use `streaming_json` for exceptionally large arrays rather than fully decoding them first.
11. Use process isolation only for parsers that genuinely need it; commands stay explicit and shell-free.
12. A failed/rate-limited/canceled local or remote source must not mark listings disappeared for that cycle.
13. Distributed workers discover/parse source data but never independently write canonical catalog/history/promotion state.
14. Prefer authenticated v2 remote execution for new deployments: worker HMAC identity, TLS/mTLS, replay rejection, lease ownership and coordinator epoch fencing are independent invariants.
15. Never give worker nodes the admin token merely for lifecycle operations; use worker self-drain and admin drain/undrain separately.
16. Preserve deterministic task/batch IDs and immutable result digests; retries cannot duplicate accepted observations merely because a worker/coordinator restarted.
17. Capability/resource/locality constraints are scheduling requirements, not evidence about hardware product performance.
18. Active/standby task-state failover must not become multi-master canonical history and must not be described as quorum consensus.
19. Preserve exact configuration, verification date, price/source URL and listing status.
20. Record source/seller/SKU confidence when supported; never substitute seller confidence for exact-SKU confidence.
21. Distinguish included/fixed RAM from board-verified maximum and CPU theoretical maximum. Add board memory source URL/date when available.
22. Preserve dimensions, DC input, PSU/cooling and host requirements when they affect deployment.
23. Unknown performance is valid. Never fill missing throughput with TOPS-based arithmetic.
24. Real vendor/community/local performance preserves model/runtime/workload/quantization/context provenance; multi-source ranges require compatible independent sources.
25. Keep specialist vision/audio metrics separate from LLM throughput and keep synthetic hardware-class runtime baselines out of product-performance evidence.
26. Keep sold-out/EOL references when technically useful, with lifecycle/availability labels and separate used-market history.
27. Regenerate `PARTS.md` after canonical catalog changes and run governance/async-blocking/catalog/tests; material distributed changes also run fault and performance gates.
28. Update README, CHANGELOG, TODO and relevant specs whenever behavior or the next-work sequence changes.
