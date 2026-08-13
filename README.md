# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware, with a bounded, authenticated multi-node discovery runtime.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty APUs and useful decommissioned accelerators. Hardware can be cataloged without being physically owned; performance claims remain separate from product/source evidence.

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

## Runtime architecture

The discovery path scales from one low-power node to multiple authenticated workers without making canonical history multi-master:

```text
                       llm-cluster-service
                              │
                  automatic secure cycle submit
                              ▼
                   ACTIVE COORDINATOR (epoch N)
                    TLS + optional mTLS
                 admin bearer / worker HMAC
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
          worker A         worker B         worker C
        capabilities      capabilities      capabilities
       locality labels   locality labels   locality labels
       CPU/RAM/thermal   CPU/RAM/thermal   CPU/RAM/thermal
        power budget      power budget      power budget
             │                │                │
             └──── bounded source observation batches ────┐
                                                         ▼
                                         SHA-256 content-addressed
                                              result artifacts
                                                         │
                                               streamed NDJSON
                                                         ▼
                                             canonical collector
                                             one SQLite writer
```

An optional standby coordinator shares durable task state and claims a new **leader epoch** after the old leader lease expires. Every secure task lease is epoch-fenced, so a stale leader/worker cannot complete or append batches after failover.

Core invariants:

- native async HTTP through reusable `aiohttp` pools;
- bounded source workers, URL workers, queues, HTTP connections and transform workers;
- `ETag` / `Last-Modified` conditional requests with parsed-observation reuse on `304`;
- retry/backoff/jitter and `Retry-After` handling;
- adaptive source concurrency, circuit breakers and adaptive observation batches;
- cache TTL, bounded entry count, LRU-style pruning and optional gzip persistence;
- true streaming large-JSON ingestion through `ijson`;
- optional process-isolated source adapters;
- incremental SQLite writes and disk-backed normalized spooling;
- failed/canceled sources are excluded from disappearance detection;
- authenticated v2 workers use leases, heartbeats, replay-protected HMAC requests and leader epochs;
- result batches and reusable source snapshots can live in immutable SHA-256-addressed storage;
- canonical history/promotion remains single-writer on the collector side.

See [docs/CONCURRENCY.md](docs/CONCURRENCY.md), [docs/DISTRIBUTED_RUNTIME.md](docs/DISTRIBUTED_RUNTIME.md), [docs/DISTRIBUTED_SECURITY.md](docs/DISTRIBUTED_SECURITY.md) and [docs/DASHBOARD.md](docs/DASHBOARD.md).

## Install and configure

```bash
python -m pip install -e .
cp config/discovery.example.json config/discovery.local.json
# Edit sources; remove example.invalid before live use.
```

Optional native OTLP/HTTP telemetry:

```bash
python -m pip install -e '.[telemetry]'
```

A representative local discovery configuration remains conservative:

```json
{
  "agent_workers": 4,
  "subworkers_per_agent": 4,
  "normalize_workers": 2,
  "http_concurrency": 16,
  "http_per_host": 4,
  "retry_attempts": 3,
  "adaptive_concurrency": true,
  "circuit_breaker": true,
  "adaptive_batching": true,
  "adaptive_batch_min": 64,
  "adaptive_batch_max": 2048,
  "cache_ttl_s": 604800,
  "cache_max_entries": 10000,
  "cache_compress": true
}
```

## One-shot local discovery

```bash
llm-cluster discover \
  --config config/discovery.local.json \
  --history results/catalog-history.sqlite3 \
  --output results/discovery-latest.json
```

Discovery/history output is **staging evidence**. It is not automatically canonical product truth.

## Persistent local service, health and metrics

```bash
llm-cluster-service \
  --config config/discovery.local.json \
  --interval 300 \
  --health-host 127.0.0.1 \
  --health-port 8787
```

Endpoints:

```text
GET /healthz     process/liveness state
GET /readyz      readiness and last-cycle freshness
GET /metrics     Prometheus text exposition
GET /v1/status   JSON health + runtime metrics snapshot
```

Prometheus remains the dependency-light default. `--otlp-endpoint http://otel-collector:4318` additionally exports native OTLP/HTTP traces/counters when the `telemetry` extra is installed.

## Secure distributed quick start

### 1. Create worker/admin credentials

```bash
llm-cluster-distributed init-auth \
  --output config/distributed-auth.json \
  --worker thinkpad-l14 \
  --worker thinkpad-t480
```

The generated file is mode `0600`; secrets are not printed. Keep it out of Git.

### 2. Start the active coordinator

```bash
llm-cluster-distributed coordinator \
  --auth-file config/distributed-auth.json \
  --state results/distributed-tasks.sqlite3 \
  --artifacts results/distributed-artifacts \
  --node-id coordinator-a \
  --host 0.0.0.0 --port 8788 \
  --tls-cert /etc/lpllm/coordinator.crt \
  --tls-key /etc/lpllm/coordinator.key \
  --tls-client-ca /etc/lpllm/ca.crt \
  --require-client-cert
```

The old unauthenticated `/v1` coordinator remains available only when `--auth-file` is omitted for compatibility. New deployments should use secure v2.

### 3. Start workers

```bash
llm-cluster-distributed worker \
  --coordinator https://coordinator.internal:8788 \
  --config config/discovery.local.json \
  --worker-id thinkpad-l14 \
  --worker-secret-file /run/secrets/lpllm-worker-secret \
  --capability json --capability jsonld --capability process \
  --label region=trailer \
  --power-budget-w 35 \
  --shared-snapshot-dir /shared/lpllm/source-snapshots \
  --tls-ca /etc/lpllm/ca.crt \
  --tls-cert /etc/lpllm/thinkpad-l14.crt \
  --tls-key /etc/lpllm/thinkpad-l14.key
```

Workers advertise capabilities, labels and current CPU/RAM/thermal state. Optional power/energy budgets are operator-supplied boundaries. Sources may request capabilities/labels, resource ceilings and preferred worker affinity.

### 4. Let the daemon own recurring distributed cycles

```bash
llm-cluster-service \
  --config config/discovery.local.json \
  --distributed-coordinator https://coordinator.internal:8788 \
  --distributed-admin-token-file /run/secrets/lpllm-admin-token \
  --distributed-tls-ca /etc/lpllm/ca.crt \
  --interval 300
```

The daemon now performs **submit → wait → streamed collect → canonical history write** automatically on every interval. No separate operator collection phase is required.

The hardened systemd installer accepts the same distributed coordinator/token-file/TLS/OTLP options:

```bash
llm-cluster-install-service \
  --config config/discovery.local.json \
  --distributed-coordinator https://coordinator.internal:8788 \
  --distributed-admin-token-file /run/secrets/lpllm-admin-token \
  --distributed-tls-ca /etc/lpllm/ca.crt \
  --enable-now
```

## Capability/locality-aware source scheduling

A source may express worker requirements:

```json
{
  "name": "special-source",
  "type": "process",
  "command": ["python", "plugins/special_source.py"],
  "worker_affinity": ["thinkpad-l14"],
  "worker_requirements": {
    "capabilities": ["process"],
    "labels": {"region": "trailer"},
    "max_cpu_load": 0.8,
    "max_thermal_c": 85,
    "min_available_memory_mb": 2048,
    "min_power_budget_w": 25
  }
}
```

Hard requirements must match. Affinity is preferred, then compatible workers may steal the task after the configured wait period so an offline preferred node does not stall a whole cycle forever.

## Result streaming and immutable artifacts

Secure result batches are persisted independently by SHA-256. The coordinator stores only artifact digest/count metadata in task state, making retried `(task_id,batch_id)` insertion idempotent.

Collectors consume `/v2/cycles/<id>/results.ndjson` one batch at a time. A complete remote cycle is never returned as one giant JSON document.

Shared source snapshots use the same content-addressed idea for normal full-body HTTP fetches. Snapshot replay is explicit (`--prefer-snapshot`) and freshness-bounded; stale data never silently becomes live truth. Streaming `ijson` feeds are not re-materialized merely to snapshot them.

## Drain, cancel and rolling restart

```bash
llm-cluster-distributed workers --coordinator ... --admin-token-file ...
llm-cluster-distributed drain --coordinator ... --worker-id thinkpad-l14 --admin-token-file ...
# restart worker
llm-cluster-distributed undrain --coordinator ... --worker-id thinkpad-l14 --admin-token-file ...
llm-cluster-distributed cancel --coordinator ... --cycle-id service-... --admin-token-file ...
```

A secure worker self-drains on SIGINT/SIGTERM without possessing admin authority, takes no new lease, finishes/losses its current lease, then exits. Repeated failing workers are temporarily quarantined.

Rolling restart sequence: **drain → wait idle/current lease → restart → undrain → next worker**.

## Coordinator backup and active/standby failover

Live backup:

```bash
llm-cluster-distributed backup \
  --coordinator https://coordinator.internal:8788 \
  --admin-token-file /run/secrets/lpllm-admin-token \
  --destination /backups/lpllm-coordinator.sqlite3
```

Offline restore:

```bash
llm-cluster-distributed restore-state \
  --backup /backups/lpllm-coordinator.sqlite3 \
  --state results/distributed-tasks.sqlite3
```

A standby coordinator can share the durable task DB/artifact store and run with `--standby`. When the active leadership lease expires, the standby increments the epoch and becomes active. Old-epoch lease mutations are rejected.

This is **fenced active/standby failover**, not quorum consensus and not SQLite multi-master replication. Canonical catalog history remains one active collector/writer.

## Very large JSON feeds

```json
{
  "name": "large-feed",
  "type": "json",
  "endpoint": "https://example.invalid/catalog.json",
  "items_path": "products",
  "streaming_json": true
}
```

`ijson` consumes array items directly from the `aiohttp` response stream, so the complete decoded source document is not required in memory.

## Process-isolated adapters

A source may use `type: "process"` with a command array. The child receives source configuration as one JSON line on stdin and returns one observation per JSONL line or `{"observations": [...]}`. The command runs without a shell, with bounded line size/runtime.

## Fault injection and performance regression tooling

```bash
python scripts/run_distributed_faults.py
python scripts/benchmark_discovery_pipeline.py --counts 1000 10000 --output results/discovery-perf.json
python scripts/check_perf_regression.py --baseline benchmarks/perf-baseline.json --current results/discovery-perf.json
python scripts/check_hardware_class_baseline.py --current results/discovery-perf.json
python scripts/profile_jsonld.py --products 1000 10000 --repeats 2
```

The fault suite covers worker-crash lease reclamation, coordinator restart persistence, stale-epoch fencing and backup. The performance workflow retains the broad generic floor and now additionally checks a hardware-class synthetic baseline when one exists. Hardware-class runtime baselines are **not** LLM product throughput claims.

## Evidence, not pretend precision

Performance evidence is explicitly labeled:

```text
measured_local       direct project measurement
community_measured   identifiable third-party measurement
vendor_measured      vendor workload measurement
derived_estimate     transformation of measured evidence
spec_based_estimate  weak planning clue only
unknown              valid when evidence does not exist
```

The project does **not** manufacture tokens/sec from TOPS, TFLOPS, memory bandwidth, core count or TDP. Confidence-aware ranges require multiple independent compatible measured records.

## Memory semantics matter

A barebone with a processor that theoretically supports 256GB does not contain 256GB. The catalog separates:

- `memory_capacity_gb` — included/fixed RAM;
- `max_memory_gb` — verified maximum for the actual product/board;
- `max_memory_source_url` / `max_memory_verified_on` — board evidence;
- `cpu_max_memory_gb` — CPU-theoretical maximum only;
- `memory_config_status` — included, fixed, configurable or unknown.

## Browse, report and compare

```bash
llm-cluster rank
llm-cluster list --llm-only --max-price 250
llm-cluster list --llm-only --min-sku-confidence 0.70 --sort price
llm-cluster report best_under_200
llm-cluster report high_memory_bargains
llm-cluster dashboard --output results/catalog-dashboard.html
```

The dashboard is organized as:

```text
OVERVIEW  →  BROWSE  →  INSPECT  →  COMPARE
coverage     filter      one item     up to four
```

Unknown values remain unknown, CPU-theoretical memory does not masquerade as board verification, and the shopping/catalog score remains separate from measured performance. See [docs/DASHBOARD.md](docs/DASHBOARD.md).

## Safe model-fit presets

```bash
llm-cluster fit special-amd-bc250-16g --preset 14b-q4
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

Model fit is a memory-capacity screen, not a speed predictor.

## CAD / Canada landed-cost planning

```bash
llm-cluster landed-cost \
  --price 220 --currency USD \
  --fx-rate 1.37 --fx-as-of 2026-08-12 \
  --province BC --shipping 25 --duty-rate 0.00 --brokerage-cad 15
```

The FX snapshot is explicit for reproducibility. The result is a planning estimate, not a customs/tax guarantee.

## Repository layout

```text
LowPowerLLMCluster/
├── config/discovery.example.json       discovery/runtime + worker requirements
├── data/catalog/                       reviewed canonical catalog fragments
├── data/discovery/                     staging/watch targets
├── data/performance/                   sourced performance evidence
├── docs/CONCURRENCY.md                 local runtime/backpressure design
├── docs/DISTRIBUTED_RUNTIME.md         secure worker/coordinator/HA design
├── docs/DISTRIBUTED_SECURITY.md        auth/TLS/epoch trust boundaries
├── docs/DASHBOARD.md                   dashboard UX + data boundaries
├── src/lowpower_llm_cluster/secure_distributed.py
├── src/lowpower_llm_cluster/content_store.py
├── benchmarks/perf-baseline.json
├── benchmarks/hardware-class-baselines.json
├── scripts/run_distributed_faults.py
├── scripts/check_hardware_class_baseline.py
└── PARTS.md                            generated canonical catalog
```

## Next priorities

See [TODO.md](TODO.md). With secure automatic distributed operation implemented, the next runtime-hardening layer is **credential/certificate rotation and external secret management, external object storage/CAS backends, stronger multi-failure-domain coordination where required, scheduler learning from historical source cost/failure data, artifact retention/integrity policy, long-running chaos/soak tests, deployment/bootstrap automation and real-node hardware-class baseline collection**.

The dashboard/data-UX track remains: live service/source health, discovery/history and price timelines, secure distributed worker/cycle status, model-fit/landed-cost actions, portable research views and compatible measured-performance visualizations.

## Data quality rule

**Measured ≠ published ≠ community-reported ≠ derived ≠ speculative.**
