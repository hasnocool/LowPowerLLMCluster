# Agent Workflow Specification

## Before changing the project

1. Read `docs/PROJECT_CHARTER.md` and `docs/GUARDRAILS.md`.
2. Read the relevant specification and agent skill.
3. For discovery/history/service work, read `docs/CONCURRENCY.md`; for remote execution also read `docs/DISTRIBUTED_RUNTIME.md` and `docs/DISTRIBUTED_SECURITY.md`.
4. Identify whether the change affects canonical catalog data, staging discovery/source snapshots, remote task state, evidence records or optional benchmark tooling.

## Runtime workflow rules

- Keep network I/O native-async and pooled; do not introduce blocking HTTP into async paths.
- Keep meaningful filesystem, SQLite and CPU-heavy parse/serialization work off the event loop.
- Bound coordinator tasks, source agents, source subworkers, HTTP connections, transform workers, process adapters, remote workers and queues.
- Prefer streaming batches/backpressure over materializing complete refreshes, source documents or remote cycles.
- Persist canonical discovery batches through one history writer and finalize disappearance only for successful sources.
- Honor `Retry-After`, preserve rate-limit telemetry and let adaptive concurrency back off faster than it recovers.
- Let repeated source failures open a circuit and cool down before consuming later-cycle workers.
- Keep cache TTL/entry bounds and explicit shared-snapshot freshness; long-running services must not create unbounded cache/CAS state.
- Adaptive batch changes are resource-control only; they do not alter source/evidence semantics.
- Reuse HTTP/DNS/cache/SQLite/coordinator resources in service/worker modes.
- Treat `304 Not Modified` plus cached parsed observations as a successful source result.
- Use true streaming JSON for feeds too large to materialize; after partial yield, retry at the source/task layer rather than duplicating records.
- Use process isolation only for unstable/special parsers; profiling remains the default reason for higher-overhead execution.

## Secure distributed workflow rules

- New deployed distributed paths use authenticated v2 unless a compatibility test explicitly exercises v1.
- Worker identity comes from verified HMAC/mTLS context, not an untrusted request body.
- Admin tokens and worker secrets are distinct authority domains.
- HMAC verification includes method, exact path/query, body digest, timestamp and nonce; nonces are replay-protected and clock skew is bounded.
- TLS is required for deployed v2 traffic; insecure verification is development-only.
- Remote workers discover/parse source data; canonical history/promotion remains one active collector writer.
- Coordinator tasks use durable leases/heartbeats; expired/crashed-worker leases are reclaimable.
- Every secure lease is fenced by the current coordinator leader epoch. Stale epochs may not heartbeat, append batches, fail or complete tasks.
- Remote task/batch IDs are deterministic/idempotent and result payloads are immutable content-addressed artifacts.
- Secure collection streams bounded NDJSON batches instead of a full-cycle payload.
- Capability/label/resource requirements are hard constraints; worker affinity may relax only through explicit bounded work stealing.
- Draining/quarantined workers receive no new leases; SIGTERM self-drain must not require admin credentials.
- Active/standby SQLite task-state failover is not quorum consensus and never makes canonical history multi-master.
- Only terminally successful sources participate in canonical disappearance detection.
- Shared source snapshot replay is explicit/freshness-bounded; immutable raw snapshots remain staging evidence.

## Data workflow rules

- Discovery/history/remote batches/snapshots remain staging evidence until reviewed into canonical `data/catalog/*.json` fragments.
- Preserve exact SKU/configuration/source semantics and memory evidence boundaries.
- Unknown performance is valid; never infer tokens/sec from TOPS/TFLOPS/bandwidth/TDP.
- Multi-source ranges require compatible independent measured records.
- Hardware-class synthetic runtime baselines are CI/runtime evidence only, not product throughput evidence.

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
python scripts/run_distributed_faults.py
```

For material runtime changes also run the synthetic 1k/10k benchmark, generic regression gate and hardware-class gate when a baseline exists. Performance thresholds catch catastrophic regressions rather than normal shared-runner noise.

Update README, CHANGELOG, TODO and affected specifications whenever behavior or next-work sequence changes.
