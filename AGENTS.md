# Agent Instructions

## Mandatory reading order

1. `docs/PROJECT_CHARTER.md`
2. `docs/GUARDRAILS.md`
3. relevant spec under `specs/`
4. matching skill under `.agents/skills/`
5. `docs/CONCURRENCY.md` for discovery/service/runtime work
6. `docs/DISTRIBUTED_RUNTIME.md` and `docs/DISTRIBUTED_SECURITY.md` for remote-worker/coordinator/security work
7. `docs/DASHBOARD.md` for dashboard/data-UX work

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
- The dashboard is a research console, not a raw-schema dump: preserve the Overview → Browse → Inspect → Compare hierarchy and keep decision-critical columns narrow by default.
- Dashboard unknown values remain explicit; never render a missing value as zero, and never visually present the catalog score as measured/predicted performance.
- Dashboard product details preserve price, memory, power and evidence scope/basis labels; staging/runtime data remains visually distinct from canonical catalog truth.
- Escape catalog text before HTML insertion and restrict generated external links to safe HTTP/HTTPS URLs. Keep the generated dashboard dependency-free, responsive and keyboard-usable.
- Async source/history/service/distributed code keeps blocking network/filesystem/database/meaningful parse work off the event loop.
- All task, queue, HTTP, source, normalization and remote-worker fan-out remains bounded.
- Reuse long-lived HTTP/DNS/cache/SQLite resources in service/worker modes instead of recreating them every cycle/task.
- Honor source rate limits and `Retry-After`; adaptive concurrency backs off faster than it ramps up.
- Repeatedly failing sources trip source-level circuits instead of consuming workers indefinitely.
- Cache state has lifecycle bounds (TTL/size/pruning); do not create unbounded persistent caches.
- A failed/canceled local or remote source is never treated as an empty successful source for disappearance detection.
- Streaming paths do not re-materialize whole refresh/source/cycle documents merely for convenience.
- Distributed workers execute source discovery only; canonical history/promotion remains single-writer on the collector side.
- Secure v2 worker identity comes from verified HMAC/mTLS context, never from an untrusted request-body worker ID.
- Worker/admin credentials are separate. Do not give workers coordinator-admin tokens merely to support lifecycle operations; self-drain is worker-authorized separately.
- Deployed v2 coordinator traffic uses TLS; `--tls-insecure-skip-verify` is development-only.
- Worker request signatures preserve exact method/path/body-digest/timestamp/nonce semantics and replay rejection.
- Remote task/result operations remain lease-owned, heartbeat-aware and idempotent across retries.
- Secure leases are leader-epoch fenced. A stale coordinator epoch must never append batches, extend leases or complete tasks after failover.
- Active/standby coordinator state is not distributed consensus. Do not describe SQLite/shared-storage failover as multi-master or partition-safe quorum.
- Canonical catalog/history remains single-writer even when coordinator task state has active/standby failover.
- Content-addressed artifacts/snapshots are immutable by digest; source snapshot replay is explicit and freshness-bounded.
- Remote result collection streams bounded batches; do not restore a whole-cycle materializing results API to the secure path.
- Capability/locality/resource scheduling preserves hard requirements; affinity may relax only through explicit bounded work-stealing rules.
- CPU/thermal/power scheduling labels operator-supplied power budgets separately from measured watts.
- OTLP is optional. Prometheus/health endpoints remain usable without telemetry extras.
- Process isolation is optional for unstable adapters; do not force all parsers into subprocesses/process pools without measured reason.
- Preserve source URLs, source type and verification dates.
- Experimental/EOL hardware retains risk and lifecycle labels.
- Multi-source performance ranges require independent compatible measured sources; specialist metrics remain separate from LLM throughput.
- Hardware-class synthetic runtime baselines are CI/runtime evidence, not product LLM throughput evidence.
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
- Material dashboard changes include focused view-model/render-safety/information-hierarchy tests.
- Material distributed changes include authentication, replay/lease/epoch, cancellation/reclaim and streaming-result tests plus `python scripts/run_distributed_faults.py`.
- Material runtime changes run the generic synthetic performance gate and hardware-class gate where a class baseline exists; thresholds remain broad enough for shared runners.
