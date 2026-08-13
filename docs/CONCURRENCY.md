# Concurrency and Efficiency Architecture

The catalog refresh path is designed so network, filesystem and database latency do not stall the asyncio event loop.

```text
                         E2E REFRESH
                              │
                    bounded source queue
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           agent 1         agent 2         agent N
              │               │               │
        URL subworkers   URL subworkers   URL subworkers
              └───────────────┼───────────────┘
                              ▼
                    aiohttp connection pool
                   global + per-host limits
                              │
                              ▼
                  off-loop parse/normalize
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
          normalized observations   SQLite writer actor
                                     one worker thread
                                     WAL + batched writes
                  └───────────┬───────────┘
                              ▼
                     atomic JSON output
```

## Worker levels

- `agent_workers`: number of source adapters that may run concurrently.
- `subworkers_per_agent`: default URL workers inside multi-page adapters such as JSON-LD discovery.
- per-source `subworkers`: optional override for a particularly large or rate-limited source.
- `http_concurrency`: global connection/request ceiling.
- `http_per_host`: per-origin ceiling so one marketplace cannot consume every connection.
- `normalize_workers`: bounded thread workers for synchronous normalization outside the event loop.
- `queue_size`: backpressure between producers and workers; task count does not grow with catalog size.

## Non-blocking rules

1. Network I/O uses a shared `aiohttp.ClientSession` and pooled keep-alive connections.
2. JSON and HTML parsing that can become material is moved off the event loop.
3. Filesystem reads/writes in async flows use worker threads; output replacement is atomic.
4. SQLite uses one persistent connection owned by one dedicated worker thread. It is never shared across threads.
5. Refresh persistence uses `executemany` batches rather than one query per observation.
6. History persistence and observation normalization run concurrently after discovery.
7. All queues and concurrency are bounded. Do not replace them with unbounded `create_task()` fan-out.
8. CI runs `scripts/check_async_blocking.py` to reject obvious blocking calls in the end-to-end async path.

## Tuning

The defaults target laptop/mini-PC class hardware without creating large idle overhead. Increase network workers first when sources are latency-bound. Increase normalization workers only after profiling shows normalization/parse CPU is material. Keep `http_per_host` conservative for marketplaces with rate limits.

A useful high-throughput starting point is:

```json
{
  "agent_workers": 8,
  "subworkers_per_agent": 4,
  "normalize_workers": 4,
  "queue_size": 128,
  "http_concurrency": 32,
  "http_per_host": 6
}
```

For an off-grid or low-power node, reduce `agent_workers`, `normalize_workers`, and `http_concurrency`; the same pipeline still functions with one worker at every level.
