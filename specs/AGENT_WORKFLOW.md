# Agent Workflow Specification

## Before changing the project

1. Read `docs/PROJECT_CHARTER.md` and `docs/GUARDRAILS.md`.
2. Read the relevant specification and agent skill.
3. For discovery/history/service work, also read `docs/CONCURRENCY.md`.
4. Identify whether the change affects canonical catalog data, staging discovery data, evidence records, or optional benchmark tooling.

## Runtime workflow rules

- Keep network I/O native-async and pooled; do not introduce blocking HTTP into async paths.
- Keep meaningful filesystem, SQLite and CPU-heavy parse/serialization work off the event loop.
- Bound source agents, source subworkers, HTTP connections, transform workers and queues.
- Prefer streaming batches and backpressure over materializing complete refreshes.
- Persist discovery batches through the single SQLite writer and finalize disappearance only for successful sources.
- Honor `Retry-After`, preserve rate-limit telemetry, and let adaptive concurrency back off faster than it recovers.
- Reuse HTTP/DNS/cache/SQLite resources in service mode.
- Treat `304 Not Modified` plus cached parsed observations as a first-class successful refresh result.
- Do not add process pools merely because parsing is synchronous; profile first.

## Data workflow rules

- Discovery/history is staging evidence until reviewed into canonical `data/catalog/*.json` fragments.
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

For material discovery-runtime changes, also run the synthetic performance harness and JSON-LD profiler where relevant.

Update README, CHANGELOG, TODO and affected specifications whenever behavior or the next-work sequence changes.
