# Distributed Discovery Runtime

LowPowerLLMCluster can execute source discovery on multiple machines while keeping one canonical catalog-history writer. The design deliberately separates **parallel source work** from **canonical history/promotion state**.

```text
                COORDINATOR / CANONICAL NODE

 config -> cycle -> durable SQLite task queue
                   │
          leases + heartbeats
          idempotent batch IDs
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     worker A   worker B   worker C
        │          │          │
     source      source      source
     adapter     adapter     adapter
        │          │          │
        └──── observation batches ────┐
                                      ▼
                             collect completed cycle
                                      │
                           one CatalogHistory writer
                                      │
                              atomic latest output
```

## Why canonical history stays single-writer

Remote nodes perform the latency-heavy source requests and parsing. They do **not** independently decide disappearance, promotion or canonical catalog state. A collector on the canonical node accepts completed remote batches, writes them through `CatalogHistory`, and runs disappearance detection only for sources whose remote tasks completed successfully. This avoids multi-master catalog conflicts while still distributing the expensive discovery stage.

## Coordinator

Start a durable coordinator:

```bash
llm-cluster-distributed coordinator \
  --state results/distributed-tasks.sqlite3 \
  --host 0.0.0.0 --port 8788
```

The coordinator persists cycles, task leases, heartbeat timestamps, attempt counts and result-batch identities in SQLite/WAL. If a worker disappears, an expired lease returns to the queue and another worker can resume it.

## Submit a cycle

```bash
llm-cluster-distributed submit \
  --coordinator http://coordinator:8788 \
  --config config/discovery.local.json \
  --cycle-id refresh-2026-08-12T1940
```

Task IDs are derived deterministically from the cycle ID and source name. Re-submitting the same cycle is therefore idempotent instead of creating duplicate source jobs.

## Workers

Run one or more workers on cluster nodes:

```bash
llm-cluster-distributed worker \
  --coordinator http://coordinator:8788 \
  --config config/discovery.local.json \
  --worker-id thinkpad-l14
```

Each worker leases one source task, keeps the lease alive with heartbeats, executes the same source-adapter contract used locally, and uploads deterministic batch IDs. Re-uploading an already accepted batch is harmless. Failed tasks are requeued until `--max-attempts` is reached.

A worker can use JSON, JSON-LD, true streaming JSON, or configured process-isolated adapters. HTTP/DNS/cache resources are reused while the worker process remains alive.

## Collect into canonical history

After the cycle completes:

```bash
llm-cluster-distributed collect \
  --coordinator http://coordinator:8788 \
  --cycle-id refresh-2026-08-12T1940 \
  --config config/discovery.local.json \
  --history results/catalog-history.sqlite3 \
  --output results/discovery-latest.json \
  --wait
```

Only completed remote sources participate in disappearance detection. A terminally failed source is reported as an error and is not treated as an empty successful source.

## Lease and retry guarantees

- One current lease owner may mutate a leased task.
- Heartbeats extend the lease only for the current unexpired owner.
- Expired leases are reclaimed before new work is selected.
- Batch IDs are unique per task; duplicates are ignored.
- Task attempt count is durable across workers.
- A retried worker uses deterministic batch numbering, so a repeated partial run cannot duplicate already accepted batches.
- Canonical history remains separate from coordinator task state.

## Network security status

The initial coordinator API is intentionally small but **does not yet provide built-in authentication or TLS/mTLS**. Until authenticated worker identities are implemented, bind it to a trusted/private network, a VPN, or a reverse proxy that supplies transport security and access control. Do not expose the coordinator directly to the public Internet.

## Current scaling boundary

The coordinator results endpoint currently materializes the cycle's stored result rows for collection. This is adequate for the first multi-node implementation and preserves retry correctness, but it is not the final large-scale transport. The next runtime phase should stream/chunk remote result batches or move large payloads through content-addressed/object storage, add authenticated worker capabilities, and automate distributed submit/wait/collect cycles inside persistent service mode.
