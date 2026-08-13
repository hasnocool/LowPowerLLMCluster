# Agent Workflow Specification

## Before changing the project

1. Read `docs/PROJECT_CHARTER.md` and `docs/GUARDRAILS.md`.
2. Read the relevant specification and agent skill.
3. For discovery/history/service work, read `docs/CONCURRENCY.md`; for remote execution also read `docs/DISTRIBUTED_RUNTIME.md`.
4. Identify whether the change affects canonical catalog data, staging discovery data, remote task state, evidence records or optional benchmark tooling.

## Runtime workflow rules

- Keep network I/O native-async and pooled; do not introduce blocking HTTP into async paths.
- Keep meaningful filesystem, SQLite and CPU-heavy parse/serialization work off the event loop.
- Bound source agents, source subworkers, HTTP connections, transform workers, process adapters, remote workers and queues.
- Prefer streaming batches and backpressure over materializing complete refreshes/documents.
- Persist canonical discovery batches through the single history writer and finalize disappearance only for successful sources.
- Honor `Retry-After`, preserve rate-limit telemetry, and let adaptive concurrency back off faster than it recovers.
- Let repeated source failures open a circuit and cool down before consuming later-cycle workers.
- Keep cache TTL/entry-size bounds; service mode must not create indefinitely growing cache state.
- Adaptive batch changes must be resource-control only; they may not alter source/evidence semantics.
- Reuse HTTP/DNS/cache/SQLite resources in service and remote-worker modes.
- Treat `304 Not Modified` plus cached parsed observations as a first-class successful source result.
- Use true streaming JSON for feeds too large to materialize; once a stream has emitted records, retry at the source/task layer rather than duplicating partial items.
- Use process isolation only for unstable/special parsers; profiling remains the default reason for higher-overhead execution.

## Distributed workflow rules

- Remote workers discover/parse source data; they do not become canonical history or catalog writers.
- Coordinator tasks use durable leases and heartbeats. Expired leases must be reclaimable.
- Remote batch IDs must be deterministic/idempotent so retries cannot duplicate accepted batches.
- Only terminally successful remote sources participate in canonical disappearance detection.
- Keep coordinator network security limitations explicit until authenticated identities and TLS/mTLS are implemented.
- Do not silently convert the distributed coordinator into multi-master canonical state.

## Data workflow rules

- Discovery/history/remote batches remain staging evidence until reviewed into canonical `data/catalog/*.json` fragments.
- Preserve exact SKU/configuration/source semantics and memory evidence boundaries.
- Unknown performance is valid; never infer tokens/sec from TOPS/TFLOPS/bandwidth/TDP.
- Multi-source ranges require compatible independent measured records.

## Required validation

Run:

```bash
python scripts/check_governance.py
python scripts/check_async_blocking.py
python scripts/validate_catalog.py
python scripts/validate_evidence_records.py
python scripts/validate_benchmark_profiles.py
python scripts/render_parts_table.py
pytest -q
```

For material runtime changes also run the synthetic 1k/10k benchmark and `scripts/check_perf_regression.py`. Performance thresholds should catch catastrophic regressions, not fail on normal shared-runner noise.

Update README, CHANGELOG, TODO and affected specifications whenever behavior or the next-work sequence changes.
