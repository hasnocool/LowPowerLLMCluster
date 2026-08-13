# TODO

## Completed in v0.5.0 — automated catalog intelligence, E2E efficiency and runtime resilience

- [x] Build bounded asynchronous JSON/JSON-LD product discovery with hierarchical source workers and backpressure.
- [x] Use pooled native `aiohttp`, keep-alive/DNS reuse, per-host limits, conditional `ETag`/`Last-Modified` requests and bounded retry/backoff/`Retry-After` handling.
- [x] Keep meaningful network/filesystem/database/parse work off the asyncio event loop and enforce it in CI.
- [x] Add adaptive per-source concurrency and per-source circuit breakers with cooldown/half-open recovery.
- [x] Add conditional-cache TTL expiration, LRU-style pruning, maximum-entry bounds and optional gzip persistence.
- [x] Add adaptive observation batch sizing from batch latency and RSS pressure rather than one fixed streaming batch size.
- [x] Add persistent `llm-cluster-service` operation reusing HTTP/DNS/cache/SQLite/worker resources across cycles.
- [x] Add `/healthz`, `/readyz`, `/metrics` and `/v1/status`; metrics use Prometheus exposition and are directly scrapeable by an OpenTelemetry Collector Prometheus receiver.
- [x] Add `llm-cluster-install-service` systemd user/system installer with absolute paths, restart policy, conservative scheduling priority and service hardening.
- [x] Add incremental SQLite refresh writes, normalized JSONL spooling and bounded streaming transforms so complete refreshes need not stay in RAM.
- [x] Add true streaming JSON-feed parsing through `ijson` so very large JSON arrays can be processed without first materializing the entire decoded document.
- [x] Add optional `process` source adapters for isolating unstable third-party parsers behind a bounded JSON-in/JSONL-out subprocess contract.
- [x] Add a durable distributed source-worker backend with coordinator cycles, leases, heartbeats, lease reclamation, retry attempts and one canonical history collector.
- [x] Add deterministic task/batch IDs and idempotent remote result insertion so worker retries/resumption do not duplicate accepted batches.
- [x] Keep failed local or remote sources out of disappearance detection for that cycle.
- [x] Add synthetic 1k/10k performance regression gates with deliberately broad shared-runner throughput/RSS/event-loop-lag thresholds.
- [x] Retain the JSON-LD parser profiler; current measurements still do not justify making process pools the default parsing path.
- [x] Add historical pricing/change tracking, seller/source/SKU confidence, board-memory evidence, CAD landed-cost planning, catalog reports/dashboard and sourced performance evidence.

## Highest priority — next secure/distributed operations work

- [ ] Integrate distributed submit/wait/collect directly into `llm-cluster-service` so recurring multi-node cycles are automatic rather than separate CLI phases.
- [ ] Add authenticated worker identities plus coordinator authorization and TLS/mTLS support; keep the current coordinator private-network-only until then.
- [ ] Stream/chunk coordinator result batches or use content-addressed/object storage so collection does not materialize a complete distributed cycle response in memory.
- [ ] Add worker capability advertisements, source affinity/locality hints and work stealing so tasks land on nodes best suited to each adapter/source.
- [ ] Add explicit drain/cancel semantics, dead-worker quarantine and graceful rolling restart behavior.
- [ ] Add coordinator backup/restore and optional HA/failover for lease/task state without turning canonical catalog history into multi-master state.
- [ ] Add native OTLP traces/metrics export as an optional dependency while retaining the dependency-light Prometheus endpoint.
- [ ] Feed CPU load, thermal state and optional energy/power budgets into concurrency/batch controllers in addition to latency/RSS.
- [ ] Add network-partition, coordinator-restart, worker-crash and duplicate-delivery fault-injection tests.
- [ ] Replace the broad generic performance floor with hardware-class baselines after enough stable CI/real-node runs are collected.
- [ ] Add cache compaction/content-addressed raw-source snapshots so multiple workers can safely share immutable source payload evidence.

## Highest priority — next catalog/source work

- [ ] Add source-specific marketplace/API adapters where generic JSON/JSON-LD is insufficient (eBay, AliExpress/Alibaba exports, used-market feeds and retailer APIs).
- [ ] Add automatic promotion proposals from high-confidence discovery observations into reviewed catalog fragments with human-readable diffs; never auto-promote unreviewed remote worker output.
- [ ] Add a pluggable live FX-rate provider while preserving explicit-rate/offline reproducibility.
- [ ] Backfill `max_memory_source_url`, dimensions, DC input and exact configuration evidence across legacy catalog records.
- [ ] Promote the highest-confidence discovery-watchlist targets into `data/catalog/` after exact SKU, price and availability verification.
- [ ] Expand exact-SKU coverage for Ryzen 7840HS/8845HS/8945HS/HX370 systems, especially 64–128GB-capable bargains.
- [ ] Add more direct-China and used-market mobile boards, mini PCs, RK3588/RK3576 systems and unusual accelerators.
- [ ] Add exportable named dashboard filter sets (JSON) so saved views can be shared between machines.

## Evidence & estimates — next

- [ ] Ingest more independent real-world records for identical hardware/model/runtime signatures.
- [ ] Add explicit provenance validators for runtime version, model artifact/hash, context length and quantization before records are range-compatible.
- [ ] Add result deduplication/fingerprints so mirrored benchmark posts do not count as independent sources.
- [ ] Import reproducible BC-250/RK3588/Jetson/Hailo/SOPHGO community results while preserving vendor/community distinctions.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.

## Optional benchmark tooling — maintenance

- [ ] Keep `llm-cluster-bench` adapters healthy as runtimes and output formats change.
- [ ] Add source-specific third-party benchmark import profiles on top of the generic importer.
- [ ] Add regression fixtures for every supported vendor/runtime adapter version.
