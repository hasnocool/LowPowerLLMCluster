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
                    conditional HTTP cache
                    TTL + prune + optional gzip
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

Circuit state is source-level rather than request-level so one source that repeatedly fails does not consume workers on every service cycle.

## Conditional cache lifecycle

The parsed-observation cache stores HTTP validators and small-enough parsed results. It now has:

- `cache_ttl_s` expiration;
- `cache_max_entries` bounds;
- LRU-style pruning using last-access time;
- optional `cache_compress` gzip persistence;
- metrics for hits, saved bytes, expiry, eviction and pruning.

A `304 Not Modified` can therefore skip body transfer and parsing while stale cache records eventually disappear from long-running services.

## Retry and adaptive source concurrency

Retryable `429`, `500`, `502`, `503` and `504` responses use bounded exponential backoff/jitter. `Retry-After` is honored when present. Adaptive source permits use AIMD-like behavior: failures/rate limits reduce concurrency quickly; sustained healthy low-latency requests recover permits slowly.

## Adaptive batch sizing

`AdaptiveBatchSizer` replaces one globally fixed observation batch size for large sources. Each source starts at `adaptive_batch_initial`, bounded by `adaptive_batch_min`/`adaptive_batch_max`. High batch wall latency or RSS above `adaptive_batch_rss_soft_limit_mb` halves the target. Sustained healthy low-latency batches increase it gradually. Current target/latency/RSS/increase/decrease counters are included in runtime telemetry.

This adapts memory and transaction size without changing source identity or history semantics.

## True streaming JSON

Normal JSON adapters may still decode a modest feed as one document. Sources with `streaming_json: true` use `ijson` over the `aiohttp` stream and emit mapped product records incrementally. This avoids retaining the decoded source document in RAM.

Because a partially yielded HTTP stream cannot be safely retried without duplicates, streaming HTTP retries are permitted only before the first yielded item. Once data has escaped the adapter, a network failure fails the source task and relies on source-level retry/lease behavior.

## Process isolation

`type: process` sources use an explicit command array with no shell. The child receives source configuration on stdin and emits bounded JSONL observations on stdout. Runtime and line size are limited. This is an escape hatch for unstable third-party parsers; ordinary built-ins remain in the cheaper thread/off-loop path unless profiling proves otherwise.

## Persistent service health

`llm-cluster-service` keeps HTTP/DNS/cache/SQLite/normalization resources alive across cycles and exposes:

- `/healthz` — liveness;
- `/readyz` — readiness based on last cycle status/freshness;
- `/metrics` — Prometheus exposition;
- `/v1/status` — JSON health + metrics.

An OpenTelemetry Collector can ingest `/metrics` with its Prometheus receiver without adding a large telemetry SDK to every low-power node.

## systemd deployment

`llm-cluster-install-service` renders or installs a user/system systemd unit with absolute data/config paths, `Restart=on-failure`, restart delay, conservative CPU/I/O scheduling, `NoNewPrivileges`, `PrivateTmp`, restrictive umask and a clean SIGTERM stop path.

## Distributed source execution

Distributed workers move only **source discovery** away from the canonical node. The coordinator's durable task store provides leases, heartbeats, lease reclamation, attempts and idempotent batch IDs. After the remote cycle is terminal, one collector writes canonical history and runs disappearance detection only for successfully completed sources.

See [DISTRIBUTED_RUNTIME.md](DISTRIBUTED_RUNTIME.md).

## Performance guard

`scripts/benchmark_discovery_pipeline.py` measures 1k/10k synthetic refresh throughput, peak RSS and event-loop lag. `scripts/check_perf_regression.py` compares results with `benchmarks/perf-baseline.json`. Thresholds are intentionally wide enough for shared GitHub runners: this check is for catastrophic regression detection, not microbenchmark enforcement.

## Non-blocking rules

1. Network I/O stays native async and pooled.
2. Filesystem, SQLite and material JSON/HTML CPU work stay off the event loop.
3. Fan-out remains bounded at source, URL, HTTP, transform and queue levels.
4. A failed/rate-limited source never masquerades as an empty successful source.
5. Streaming paths do not re-materialize whole refreshes merely for convenience.
6. Distributed workers never write canonical catalog/history state directly.
7. Process isolation remains optional and profiling-driven.
8. `scripts/check_async_blocking.py` mechanically guards the local, service and distributed async paths.

## Next layer

The next runtime work is authenticated/TLS-protected workers, automatic distributed cycles inside the service, streamed/chunked remote result transport, worker capability scheduling, drain/cancel/restart semantics, coordinator recovery/HA, optional native OTLP export and fault-injection testing. See `TODO.md`.
