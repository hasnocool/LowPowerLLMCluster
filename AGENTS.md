# Agent Instructions

## Mandatory reading order

1. `docs/PROJECT_CHARTER.md`
2. `docs/GUARDRAILS.md`
3. relevant spec under `specs/`
4. matching skill under `.agents/skills/`
5. `docs/CONCURRENCY.md` for discovery/service/runtime work
6. `docs/DISTRIBUTED_RUNTIME.md` for remote-worker/coordinator work

## Project purpose

LowPowerLLMCluster is primarily a **catalog, sourcing and buying/research planner** for efficient and unusual local-AI hardware. Benchmarking is optional evidence tooling, not the main project.

## Rules that may not be traded away

- Preserve plain-language explanations and useful ASCII diagrams.
- Grow the catalog even when hardware cannot be locally tested.
- Keep manufacturer, seller, community, benchmark and derived-estimate claims distinct.
- Unknown performance is better than fabricated precision.
- Never derive tokens/sec directly from TOPS/TFLOPS/bandwidth/core count/TDP.
- `memory_capacity_gb` means included/fixed memory; barebones do not inherit CPU maximum RAM.
- Capacity/model-fit estimates must expose assumptions and warn that they are not throughput predictions.
- Machine-readable catalog fragments are authoritative; generated docs follow them.
- Discovery/history/remote-worker data is staging evidence until reviewed into canonical catalog fragments.
- Async source/history/service/distributed code must keep blocking network/filesystem/database/meaningful parse work off the event loop.
- All task, queue, HTTP, source, normalization and remote-worker fan-out must remain bounded.
- Reuse long-lived HTTP/DNS/cache/SQLite resources in service/worker modes instead of recreating them every cycle/task.
- Honor source rate limits and `Retry-After`; adaptive concurrency must back off faster than it ramps up.
- Repeatedly failing sources should trip source-level circuits instead of consuming workers indefinitely.
- Cache state must have lifecycle bounds (TTL/size/pruning); do not create unbounded persistent caches.
- A failed local or remote source must not be treated as an empty successful source for disappearance detection.
- Streaming paths must not re-materialize the whole refresh/source document merely for convenience.
- Distributed workers execute source discovery only; canonical history/promotion decisions remain single-writer on the coordinator/collector side.
- Remote task/result operations must remain lease-owned, heartbeat-aware and idempotent across retries.
- The initial distributed coordinator has no built-in auth/TLS; do not document it as safe for public exposure.
- Process isolation is optional for unstable adapters; do not force all parsers into subprocesses/process pools without measured reason.
- Preserve source URLs, source type and verification dates.
- Experimental/EOL hardware retains risk and lifecycle labels.
- Multi-source performance ranges require independent compatible measured sources; specialist metrics remain separate from LLM throughput.
- Benchmark code remains available but must not become a prerequisite for catalog inclusion/ranking.
- Update README, PARTS, CHANGELOG, TODO and relevant docs/specs with behavior changes.
- Use semantic versioning and Python 3.12+.

## Release/document invariants

- `VERSION`, `pyproject.toml`, package `__version__`, and latest CHANGELOG version agree.
- `python scripts/check_governance.py` passes.
- `python scripts/check_async_blocking.py` passes.
- `python scripts/validate_catalog.py` passes.
- `python scripts/validate_evidence_records.py` passes.
- `python scripts/validate_benchmark_profiles.py` passes.
- `python scripts/render_parts_table.py` leaves `PARTS.md` clean.
- `pytest -q` passes.
- Material runtime changes run the synthetic performance gate; the threshold must remain broad enough for shared runners rather than becoming a flaky microbenchmark.
