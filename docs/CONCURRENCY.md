# Concurrency and Efficiency Architecture

The catalog refresh path is designed so network, filesystem, parsing and database latency do not stall the asyncio event loop, while concurrency remains bounded enough for laptop/mini-PC/off-grid nodes.

```text
                     LOCAL OR REMOTE SOURCE TASK
                                 │
                         source circuit breaker
                         closed/open/half-open
                                 │
                    adaptive source concurrency
                                 │
                   aiohttp connection/DNS pool
                         retry + Retry-After
                                 │
              conditional cache / shared CAS snapshot
                                 │
                  streamed observation batches
                                 │
                     adaptive batch controller
                     latency + RSS feedback
                                 │
                  ┌──────────────┴──────────────┐
                  ▼                             ▼
          off-loop normalization        SQLite writer actor
                  │                     incremental WAL commits
                  └──────────────┬──────────────┘
                                 ▼
                      normalized JSONL spool
                                 │
                                 ▼
                         atomic latest JSON
```

## Circuit breakers

Every source adapter can be wrapped in `CircuitProtectedAdapter`. Repeated failed cycles open that source's circuit. While open, later refresh cycles reject the source before it consumes HTTP/subworker capacity. After `circuit_recovery_timeout_s`, a bounded half-open probe is allowed. A successful probe closes the circuit; a failed probe immediately reopens it.

## Conditional cache lifecycle

The parsed-observation cache stores HTTP validators and small-enough parsed results with TTL expiration, bounded entry count, LRU-style pruning and optional gzip persistence. A `304 Not Modified` can skip body transfer/parsing while stale records disappear over time.

Secure distributed workers can additionally use a shared SHA-256 source snapshot directory. Snapshot reuse is explicit and freshness-bounded; streaming `ijson` feeds are not re-materialized merely to create snapshots.

## Retry and adaptive source concurrency

Retryable `429`, `500`, `502`, `503` and `504` responses use bounded exponential backoff/jitter. `Retry-After` is honored. Adaptive permits back off quickly after failure/rate limiting and recover slowly after sustained healthy requests.

## Adaptive batch sizing

`AdaptiveBatchSizer` bounds per-source observation batch size between configured limits and reacts to batch wall latency/RSS pressure. This adjusts memory/transaction size without changing source identity or history semantics.

## True streaming JSON

Sources with `streaming_json: true` use `ijson` over the `aiohttp` response stream. Once a streaming adapter has emitted an item, request-level retry is no longer safe; later failures fail the source task and rely on source/task retry semantics instead.

## Process isolation

`type: process` sources use a command array without a shell. Runtime/line size are bounded. This is an isolation escape hatch for unstable third-party adapters, not the default for every parser.

## Persistent service health

`llm-cluster-service` reuses HTTP/DNS/cache/SQLite/normalization resources and exposes `/healthz`, `/readyz`, `/metrics` and `/v1/status`.

Prometheus remains dependency-light. Optional `.[telemetry]` dependencies enable native OTLP/HTTP traces/counters without making them mandatory on small nodes.

## Automatic secure distributed service mode

When `--distributed-coordinator` is configured, each service cycle becomes:

```text
submit sources → wait terminal → stream NDJSON batches → incremental history → final spool
```

The daemon reuses one secure coordinator client between cycles. It never loads an entire remote cycle result into memory.

## Distributed scheduling hierarchy

Secure v2 adds another bounded scheduling layer before source execution:

```text
queued source task
      │
      ├─ required capabilities
      ├─ required locality labels
      ├─ CPU / RAM / thermal gates
      ├─ operator power-budget gate
      ├─ preferred worker affinity
      └─ bounded work-steal timeout
      ▼
one leased worker
      │
leader epoch + heartbeat
      ▼
source's existing bounded subworkers / HTTP pool
```

A worker owns at most the lease it was granted; draining/quarantined workers receive no new leases. Hard capability/resource requirements are never relaxed by work stealing—only affinity preference is.

## Epoch-fenced active/standby

Coordinator leadership uses one short lease plus monotonically increasing epoch in durable task state. Every secure lease records that epoch. Heartbeat/batch/fail/complete operations require the current epoch, preventing an old coordinator/lease from mutating work after standby promotion.

This is active/standby fencing, not a quorum protocol. Canonical history is still single-writer.

## Content-addressed result transport

Each result batch is an immutable SHA-256 artifact. Task state stores digest/count metadata; duplicate task/batch IDs are ignored. Collection streams one NDJSON batch at a time. The secure API therefore has bounded batch memory rather than complete-cycle memory.

## Resource-aware workers

Linux workers sample load average normalized by CPU count, `/proc/meminfo` availability and thermal-zone temperatures off the event loop. Power/energy budgets are optional operator inputs; they are not inferred from TDP or treated as measured node watts.

## systemd deployment and rolling restart

`llm-cluster-install-service` can render local or secure-distributed daemon units. Secure workers self-drain on termination, while admin drain/undrain supports rolling restart:

**drain → finish/expire current lease → restart → undrain → next node**.

## Performance guards

- `scripts/check_perf_regression.py` keeps the broad cross-runner catastrophic-regression floor.
- `scripts/check_hardware_class_baseline.py` applies a class-specific synthetic runtime baseline when one is committed.
- Hardware-class runtime baselines are never catalog product throughput evidence.
- `scripts/run_distributed_faults.py` exercises worker crash reclamation, restart persistence, backup and stale-epoch rejection.

## Non-blocking rules

1. Network I/O stays native async and pooled.
2. Filesystem, SQLite and material JSON/HTML CPU work stay off the event loop.
3. Fan-out remains bounded at coordinator task, source, URL, HTTP, transform and queue levels.
4. Failed/canceled/rate-limited sources never masquerade as empty successful sources.
5. Streaming paths do not re-materialize whole source/refresh/cycle payloads for convenience.
6. Distributed workers never write canonical catalog/history directly.
7. Secure mutations require valid identity, lease ownership and leader epoch.
8. Content-addressed snapshots/results preserve immutable digest semantics and bounded retention/GC policy.
9. Process isolation remains optional and profiling-driven.
10. `scripts/check_async_blocking.py` mechanically covers local, service and secure-distributed async paths.

## Next layer

The next production-hardening layer is external secret/certificate rotation, object-store CAS, stronger consensus/state backends where separate failure domains require them, historical scheduler learning, artifact integrity/retention automation, cluster bootstrap/enrollment and long-running chaos/soak validation. See `TODO.md`.
