# Distributed Runtime

LowPowerLLMCluster keeps **source execution distributed** while keeping **canonical catalog/history single-writer**. That split is deliberate: worker failures and retries can be handled as task state without turning reviewed catalog truth into a multi-master database.

## v2 architecture

```text
                       llm-cluster-service
                    submit / wait / stream / collect
                              │ admin auth
                              ▼
                    ┌────────────────────┐
                    │ active coordinator │◄──── shared state/CAS ────┐
                    │ epoch N            │                            │
                    └─────────┬──────────┘                            │
                              │ TLS / optional mTLS                   │
                 HMAC worker identity + replay guard                 │
                              │                                      │
           ┌──────────────────┼───────────────────┐                  │
           ▼                  ▼                   ▼                  │
       worker A            worker B            worker C              │
       capabilities        capabilities        capabilities          │
       labels/locality     labels/locality     labels/locality       │
       CPU/RAM/temp        CPU/RAM/temp        CPU/RAM/temp           │
       power budget        power budget        power budget           │
           │                  │                   │                  │
           └────────── observation batches ──────┘                  │
                              │                                      │
                              ▼                                      │
                   content-addressed artifacts ──────────────────────┘
                              │
                     NDJSON streamed results
                              │
                              ▼
                  canonical history collector
                    one SQLite writer only
```

The legacy `/v1` coordinator remains available for compatibility. New secure deployments should use the authenticated `/v2` protocol.

## Automatic distributed daemon cycles

`llm-cluster-service` can now own the full remote cycle:

```bash
llm-cluster-service \
  --config config/discovery.local.json \
  --distributed-coordinator https://coordinator.internal:8788 \
  --distributed-admin-token-file /run/secrets/lpllm-admin-token \
  --distributed-tls-ca /etc/lpllm/ca.crt \
  --interval 300
```

Each service cycle:

1. submits the configured sources;
2. waits for remote tasks to reach terminal state;
3. consumes result batches incrementally through NDJSON;
4. writes observations into canonical `CatalogHistory` in batches;
5. runs disappearance detection only for completed sources;
6. writes the same normalized atomic output used by local mode.

There is no separate operator `submit → status → collect` requirement in daemon mode.

## Worker identity and authorization

Create a credential registry once:

```bash
llm-cluster-distributed init-auth \
  --output config/distributed-auth.json \
  --worker thinkpad-l14 \
  --worker thinkpad-t480
```

The file is created with mode `0600`; generated secrets are not printed. Keep the file off source control.

Worker requests carry:

- worker ID;
- timestamp;
- random nonce;
- HMAC-SHA256 signature over method, exact request path/query, body digest, timestamp and nonce.

The coordinator verifies clock skew and remembers recent nonces to reject replay. Worker identity comes from the verified signature, not from a JSON `worker_id` field supplied by the caller.

Administrative operations use a separate bearer token. Workers do **not** receive that token.

See [DISTRIBUTED_SECURITY.md](DISTRIBUTED_SECURITY.md).

## TLS and mTLS

Start a TLS coordinator:

```bash
llm-cluster-distributed coordinator \
  --auth-file config/distributed-auth.json \
  --state results/distributed-tasks.sqlite3 \
  --artifacts results/distributed-artifacts \
  --tls-cert /etc/lpllm/coordinator.crt \
  --tls-key /etc/lpllm/coordinator.key \
  --tls-client-ca /etc/lpllm/ca.crt \
  --require-client-cert
```

Workers may use both their HMAC identity and a client certificate:

```bash
llm-cluster-distributed worker \
  --coordinator https://coordinator.internal:8788 \
  --config config/discovery.local.json \
  --worker-id thinkpad-l14 \
  --worker-secret-file /run/secrets/lpllm-worker-secret \
  --tls-ca /etc/lpllm/ca.crt \
  --tls-cert /etc/lpllm/thinkpad-l14.crt \
  --tls-key /etc/lpllm/thinkpad-l14.key
```

`--tls-insecure-skip-verify` exists only as an explicit development escape hatch. Do not use it for deployed coordinators.

## Capability, locality and resource scheduling

Workers advertise capabilities and labels:

```bash
llm-cluster-distributed worker \
  ... \
  --capability json \
  --capability jsonld \
  --label region=trailer \
  --label network=starlink \
  --power-budget-w 35
```

A source can declare requirements:

```json
{
  "name": "gpu-only-source",
  "type": "process",
  "command": ["python", "plugins/gpu_source.py"],
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

Hard requirements must match. Affinity is preferred until `work_steal_after_s` elapses, after which another compatible worker may take the task. This prevents indefinite affinity starvation while still favoring data/tool locality.

Workers report a resource snapshot at registration, lease and heartbeat time. Linux workers sample CPU load, available memory and thermal zones; optional power/energy budgets are operator-supplied boundaries, not guessed wattage measurements.

## Leases, epochs and failover

Every secure lease contains a coordinator **epoch**. Heartbeats, batches, failure reports and completion must present the same epoch.

An active coordinator renews a short leadership lease in the shared coordinator database. A standby can be started with:

```bash
llm-cluster-distributed coordinator \
  --auth-file config/distributed-auth.json \
  --state /shared/lpllm/distributed-tasks.sqlite3 \
  --artifacts /shared/lpllm/artifacts \
  --node-id standby-b \
  --standby
```

When the old leader lease expires, a standby claims leadership and increments the epoch. Mutations from an older epoch are rejected. This is **active/standby failover with fencing**, not distributed consensus and not multi-master catalog history.

The coordinator state file and artifact directory must therefore reside on storage whose sharing/failure semantics you understand. Do not put SQLite itself on an unreliable network filesystem.

## Backup and restore

Create a live SQLite backup through the active coordinator:

```bash
llm-cluster-distributed backup \
  --coordinator https://coordinator.internal:8788 \
  --admin-token-file /run/secrets/lpllm-admin-token \
  --destination /backups/lpllm-coordinator.sqlite3
```

Restore is deliberately an **offline** operation:

```bash
# stop active + standby coordinators first
llm-cluster-distributed restore-state \
  --backup /backups/lpllm-coordinator.sqlite3 \
  --state results/distributed-tasks.sqlite3
```

The restore command atomically replaces the main database and removes stale WAL/SHM sidecars. Start coordinators only after restore completes.

## Content-addressed result transport

Each worker result batch is serialized independently and stored by SHA-256. Coordinator task state keeps only the digest, record count and byte count. Re-sending the same task/batch ID is idempotent.

Collection uses `application/x-ndjson` and yields one result batch at a time. A complete cycle is never required as one giant JSON response in coordinator, daemon or collector memory.

This is batch-streaming rather than byte-range upload. Very large adapters should keep batch sizes bounded.

## Shared immutable source snapshots

Workers can share a content-addressed source directory:

```bash
llm-cluster-distributed worker \
  ... \
  --shared-snapshot-dir /shared/lpllm/source-snapshots \
  --snapshot-max-age-s 300
```

Normal full-body HTTP responses are stored by SHA-256 with a small URL/ETag/Last-Modified index. `--prefer-snapshot` explicitly allows a freshness-bounded snapshot to satisfy a request. Snapshot replay is never implicit and a stale snapshot is never treated as live source truth.

Streaming `ijson` feeds preserve their low-memory network path rather than being re-materialized just to create a shared raw snapshot.

## Drain, cancel, quarantine and rolling restart

Administrative drain:

```bash
llm-cluster-distributed drain --coordinator ... --worker-id thinkpad-l14 --admin-token-file ...
```

A draining worker receives no new leases. On SIGINT/SIGTERM a secure worker self-drains without needing the admin token, finishes or loses its current lease, and exits.

After restart:

```bash
llm-cluster-distributed undrain --coordinator ... --worker-id thinkpad-l14 --admin-token-file ...
```

Cancel a cycle:

```bash
llm-cluster-distributed cancel --coordinator ... --cycle-id service-... --admin-token-file ...
```

Canceled tasks become terminal and their next heartbeat is rejected. Repeated task failures increment a worker failure counter; after the configured threshold the worker is temporarily quarantined and receives no leases until the quarantine expires or an operator intervenes.

A rolling restart is therefore: drain → wait for current lease/idle → restart → undrain → move to next worker.

## OTLP and Prometheus

Prometheus `/metrics` remains the default low-dependency path. Native OTLP/HTTP is optional:

```bash
python -m pip install -e '.[telemetry]'
llm-cluster-service ... --otlp-endpoint http://otel-collector:4318
```

When configured, the service exports traces and counters while retaining the existing Prometheus endpoint. Requesting OTLP without the optional dependencies fails with a clear installation message instead of silently disabling telemetry.

## Fault injection

Deterministic distributed fault smoke tests are available with:

```bash
python scripts/run_distributed_faults.py
```

The suite covers worker-crash lease reclamation, coordinator restart persistence, stale-epoch rejection and live backup. Unit/integration tests additionally cover duplicate batches, cancellation, capability scheduling and authentication failures.

## Hardware-class performance baselines

`benchmarks/hardware-class-baselines.json` stores synthetic **runtime** baselines keyed by execution environment. These are not product throughput claims and never become tokens/sec evidence.

```bash
python scripts/check_hardware_class_baseline.py \
  --current results/discovery-perf.json
```

The generic broad performance gate remains authoritative when no class-specific baseline exists.

## Invariants

- Remote worker output is staging evidence.
- Canonical catalog/history has one active writer.
- HMAC identity does not replace TLS confidentiality; deployed v2 traffic should use TLS.
- mTLS certificate identity is an additional transport control, not a substitute for lease ownership/epoch fencing.
- A failed/canceled source never looks like an empty successful source.
- No task/result API may require an entire cycle payload in memory.
- A stale leadership epoch may not mutate a lease.
- Snapshot reuse is explicit and freshness-bounded.
