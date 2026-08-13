# LowPowerLLMCluster

**A catalog-first research and buying planner for cheap, efficient and unusual local-LLM hardware, with a bounded multi-node discovery runtime.**

The project tracks mini PCs, laptop/mobile-CPU boards, SBCs, embedded systems, NPUs, TPUs, AI ASICs, FPGAs, specialty APUs and useful decommissioned accelerators. Hardware can be cataloged without being physically owned; performance claims remain separate from product/source evidence.

> **What can I buy, what does it cost, what can it probably fit/run, what software does it need, how efficient might it be, how strong is the evidence, and is it a good deal?**

## Runtime architecture

The discovery path now scales from one low-power node to multiple workers without making canonical history multi-master:

```text
                      DISCOVERY COORDINATOR
                              │
                   bounded source/task queue
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
          worker A         worker B         worker C
             │                │                │
       circuit breaker   circuit breaker  circuit breaker
       adaptive permits  adaptive permits adaptive permits
             │                │                │
             └──────── pooled/streamed source I/O ────────┐
                                                          ▼
                                           observation batches
                                                          │
                              ┌───────────────────────────┴──────┐
                              ▼                                  ▼
                      off-loop normalize                canonical history
                      adaptive batches                  single SQLite writer
                              │                                  │
                              └──────────────┬───────────────────┘
                                             ▼
                                  normalized JSONL spool
                                             │
                                             ▼
                                     atomic latest JSON
```

The core invariants are:

- native async HTTP through reusable `aiohttp` pools;
- bounded source workers, URL workers, queues, HTTP connections and transform workers;
- `ETag` / `Last-Modified` conditional requests with parsed-observation reuse on `304`;
- retry/backoff/jitter and `Retry-After` handling;
- adaptive per-source concurrency plus circuit breakers that cool down repeatedly failing sources;
- cache TTL, bounded entry count, LRU-style pruning and optional gzip persistence;
- adaptive observation batch sizes based on batch latency and RSS pressure;
- true streaming large-JSON ingestion through `ijson` when `streaming_json` is enabled;
- optional `process` adapters for isolating unstable third-party parsers;
- incremental SQLite writes and disk-backed normalized spooling;
- failed sources are excluded from disappearance detection;
- a persistent service can reuse HTTP/DNS/cache/SQLite state across cycles;
- distributed source workers use leases, heartbeats and idempotent batch IDs while one collector retains canonical history ownership.

See [docs/CONCURRENCY.md](docs/CONCURRENCY.md) and [docs/DISTRIBUTED_RUNTIME.md](docs/DISTRIBUTED_RUNTIME.md).

## Install and configure

```bash
python -m pip install -e .
cp config/discovery.example.json config/discovery.local.json
# Edit the sources and remove example.invalid before live use.
```

A representative runtime configuration looks like:

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

## One-shot discovery

```bash
llm-cluster discover \
  --config config/discovery.local.json \
  --history results/catalog-history.sqlite3 \
  --output results/discovery-latest.json
```

Discovery/history output is **staging evidence**. It is not automatically canonical product truth.

## Persistent service, health and metrics

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

The Prometheus endpoint is directly scrapeable by Prometheus and by an OpenTelemetry Collector using its Prometheus receiver. A native optional OTLP exporter remains future work rather than a mandatory dependency on small nodes.

Install a hardened systemd user unit:

```bash
llm-cluster-install-service \
  --config config/discovery.local.json \
  --enable-now
```

Use `--system` for `/etc/systemd/system`. The installer resolves configured paths to absolute paths and emits `Restart=on-failure`, restart backoff, conservative scheduling priority, `NoNewPrivileges`, `PrivateTmp` and a restrictive umask.

## Distributed source workers

Start the durable coordinator on the canonical node:

```bash
llm-cluster-distributed coordinator \
  --state results/distributed-tasks.sqlite3 \
  --host 0.0.0.0 --port 8788
```

Submit a source cycle:

```bash
llm-cluster-distributed submit \
  --coordinator http://coordinator:8788 \
  --config config/discovery.local.json \
  --cycle-id refresh-001
```

Run workers on one or more machines:

```bash
llm-cluster-distributed worker \
  --coordinator http://coordinator:8788 \
  --config config/discovery.local.json \
  --worker-id node-a
```

Then collect the completed remote cycle into canonical history:

```bash
llm-cluster-distributed collect \
  --coordinator http://coordinator:8788 \
  --cycle-id refresh-001 \
  --config config/discovery.local.json \
  --wait
```

Workers have durable leases and heartbeats. Expired work is reclaimed, attempts survive worker changes, task/batch IDs are deterministic, and duplicate result batches are ignored. Only completed source tasks participate in disappearance detection.

**Security note:** the initial coordinator API does not yet provide built-in authentication or TLS/mTLS. Keep it on a trusted/private network, VPN, or protected reverse proxy; do not expose it directly to the public Internet. The next runtime phase adds authenticated worker identities and transport security.

## Very large JSON feeds

For a JSON feed whose product array is too large to decode as one document, enable streaming:

```json
{
  "name": "large-feed",
  "type": "json",
  "endpoint": "https://example.invalid/catalog.json",
  "items_path": "products",
  "streaming_json": true
}
```

`ijson` consumes array items directly from the `aiohttp` response stream. The item mapping remains the same as normal JSON adapters, but the complete decoded document is never required in memory.

## Process-isolated adapters

A source may use `type: "process"` with a command array. The child receives the source configuration as one JSON line on stdin and returns either one observation per JSONL line or `{"observations": [...]}`. The command is executed without a shell, line size and runtime are bounded, and the rest of the discovery pipeline remains unchanged. This is for unstable/special third-party parsers—not a reason to move every parser into a process.

## Performance regression tooling

```bash
python scripts/benchmark_discovery_pipeline.py --counts 1000 10000 --output results/discovery-perf.json
python scripts/check_perf_regression.py \
  --baseline benchmarks/perf-baseline.json \
  --current results/discovery-perf.json
python scripts/profile_jsonld.py --products 1000 10000 --repeats 2
```

The PR performance workflow uses deliberately broad thresholds to catch catastrophic throughput/RSS/event-loop regressions without treating ordinary shared-runner noise as a failure. JSON-LD parsing remains fast enough in current measurements that a process pool is not justified as the default path.

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
llm-cluster report low_power_nodes
llm-cluster report weird_hardware
llm-cluster report eol_bargains
llm-cluster dashboard --output results/catalog-dashboard.html
```

The dashboard has been rebuilt around a four-step research flow rather than a raw catalog table:

```text
OVERVIEW  →  BROWSE  →  INSPECT  →  COMPARE
coverage     filter      one item     up to four
```

- **Overview** shows catalog size, LLM-candidate count, data completeness, catalog mix and top research candidates.
- **Browse** keeps only decision-critical columns visible: product, price, memory/evidence basis, power boundary/scope, risk, evidence source and research score.
- Selecting a row opens a structured **product inspector** for buying status, memory evidence, power/deployment requirements, software/workload support and source provenance.
- **Compare** uses a dedicated matrix for up to four products instead of compressing comparisons into prose.
- Filters and comparison state persist locally, global search supports `Ctrl/Cmd+K`, and the self-contained dashboard adapts its navigation/filter layout for smaller screens.

Unknown values remain unknown, CPU-theoretical memory does not masquerade as board verification, and the shopping/catalog score remains separate from measured performance. See [docs/DASHBOARD.md](docs/DASHBOARD.md) for the dashboard information architecture and data-boundary rules.

## Safe model-fit presets

Model fit is a memory-capacity screen, not a speed predictor:

```bash
llm-cluster fit special-amd-bc250-16g --preset 14b-q4
llm-cluster fit special-amd-bc250-16g --params-b 14 --bits 4
```

## CAD / Canada landed-cost planning

```bash
llm-cluster landed-cost \
  --price 220 --currency USD \
  --fx-rate 1.37 --fx-as-of 2026-08-12 \
  --province BC --shipping 25 --duty-rate 0.00 --brokerage-cad 15
```

The FX snapshot is explicit for reproducibility. The result is a planning estimate, not a customs/tax guarantee.

## Sourced performance records

```bash
llm-cluster performance-range data/performance/my-records.json \
  --hardware-id node-example \
  --model Example-7B \
  --runtime llama.cpp \
  --workload-class llm_decode \
  --metric tokens_per_second
```

Specialist vision/audio/embedding/reranking records remain separate from LLM throughput.

## Repository layout

```text
LowPowerLLMCluster/
├── config/discovery.example.json       discovery/runtime configuration
├── data/catalog/                       reviewed canonical catalog fragments
├── data/discovery/                     staging/watch targets
├── data/performance/                   sourced performance evidence
├── docs/CONCURRENCY.md                 local runtime/backpressure design
├── docs/DISTRIBUTED_RUNTIME.md         lease/worker/coordinator design
├── docs/DASHBOARD.md                   dashboard UX + data-boundary design
├── specs/discovery-config.schema.json  source/runtime configuration contract
├── src/lowpower_llm_cluster/           planner + local/distributed runtime
├── benchmarks/perf-baseline.json       broad synthetic regression reference
├── scripts/benchmark_discovery_pipeline.py
├── scripts/check_perf_regression.py
└── PARTS.md                            generated canonical catalog
```

## Next priorities

See [TODO.md](TODO.md). The next dashboard/data-UX phase is a **live but evidence-separated operations view**: service/source health, discovery history/change events, price-history timelines, distributed cycle state, model-fit/landed-cost actions, portable saved research views and compatible measured-performance visualizations. Secure/automatic distributed operation remains the parallel runtime priority: service-integrated remote cycles, authenticated workers and TLS/mTLS, streamed remote result transport, capability-aware scheduling, coordinator recovery/HA, resource-aware controls and fault-injection tests.

## Data quality rule

**Measured ≠ published ≠ community-reported ≠ derived ≠ speculative.**
