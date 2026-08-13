# Concurrency and Efficiency Architecture

The catalog refresh path is designed so network, filesystem, parsing and database latency do not stall the asyncio event loop, while concurrency remains bounded enough for low-power hosts.

```text
                         E2E REFRESH / SERVICE
                                  │
                         bounded source queue
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
             agent 1           agent 2           agent N
                │                 │                 │
          URL subworkers     URL subworkers     URL subworkers
                │                 │                 │
                └─────────────────┼─────────────────┘
                                  ▼
                         adaptive source permits
                        latency/error/429 feedback
                                  │
                                  ▼
                        aiohttp connection pool
                 global/per-host + keepalive + DNS cache
                                  │
                     ETag / Last-Modified cache
                     304 -> parsed observation reuse
                                  │
                                  ▼
                     streamed discovery batches
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
          bounded off-loop normalize      SQLite writer actor
                   workers                one worker thread
                    │                    WAL + batch commits
                    └─────────────┬─────────────┘
                                  ▼
                      normalized JSONL spool
                                  │
                                  ▼
                         atomic latest JSON
```

## Request efficiency

`AsyncHttpClient` uses one reusable `aiohttp.ClientSession` in service mode. It provides global/per-host connection ceilings, keep-alive/DNS reuse, response-size limits, conditional GET, retries and telemetry.

Successful responses cache `ETag` / `Last-Modified` plus parsed observations. On a later `304 Not Modified`, the adapter reuses the parsed observations and avoids both body transfer and JSON/HTML parsing. Very large feed entries intentionally stop using conditional validators once their parsed observation set exceeds `cache_observation_limit`; this keeps cache memory bounded instead of trading network savings for unbounded RAM.

Retryable `429`, `500`, `502`, `503` and `504` responses use bounded exponential backoff with jitter. `Retry-After` is honored when supplied. Retry count, rate limits, retry sleep, bytes and per-source attempt/latency totals are exposed in runtime telemetry.

## Adaptive per-source concurrency

Each source has an `AdaptiveConcurrency` controller. Rate limits/errors halve the current permit ceiling down to `adaptive_min_subworkers`. Sustained successful requests whose EWMA latency remains below `adaptive_latency_target_ms` cautiously add permits back up to the configured maximum. This is intentionally AIMD-like: back off quickly, recover slowly.

## Streaming and persistence

Discovery yields source batches instead of creating one catalog-sized list. JSON feeds emit bounded observation batches from an off-loop parser worker; JSON-LD sources emit page batches as URL workers complete. The refresh coordinator normalizes and persists each batch before accepting later work.

SQLite uses one persistent connection on one dedicated worker thread. A refresh is begun once, observations are recorded incrementally, and disappearance detection is finalized only for sources that completed successfully. This prevents a rate-limited/failed source from being falsely marked disappeared.

Normalized observations are appended to an on-disk spool and assembled into the final JSON atomically. The full normalized catalog therefore does not need to exist in RAM at one time.

## Long-running service mode

`llm-cluster-service` keeps HTTP sockets, DNS cache, conditional cache and SQLite writer alive across cycles:

```bash
llm-cluster-service \
  --config config/discovery.local.json \
  --interval 300
```

Use `--cycles N` for a finite run. SIGINT/SIGTERM stop after the current cycle/sleep boundary.

## Profiling before processes

`scripts/profile_jsonld.py` measures JSON-LD parsing directly. On the development runner, the synthetic 10,000-product page parsed at roughly 167k products/sec, while the E2E 10,000-observation path was roughly 4k observations/sec. Parsing is therefore not currently the measured bottleneck, so a process pool is deliberately not enabled by default.

`scripts/benchmark_discovery_pipeline.py` provides 100/1,000/10,000 observation fixtures and reports throughput, peak RSS, p95/max event-loop lag. `.github/workflows/perf.yml` exposes this as an optional manual performance job.

## Next optimization layer

The next runtime work is circuit breakers, cache TTL/pruning, adaptive batch sizing, health/metrics endpoints, service installation and a distributed source-worker backend with leases/heartbeats and retry-safe idempotent batches. See `TODO.md`.
