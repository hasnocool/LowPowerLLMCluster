# TODO

## Completed in v0.5.0 — catalog intelligence, resilient discovery, dashboard UX and secure automatic distributed operation

- [x] Build bounded asynchronous JSON/JSON-LD/process discovery with hierarchical workers and backpressure.
- [x] Use pooled native `aiohttp`, conditional requests, retries/`Retry-After`, adaptive concurrency and per-source circuit breakers.
- [x] Keep meaningful network/filesystem/database/parse work off the asyncio event loop and enforce it in CI.
- [x] Bound/persist cache state with TTL/LRU/entry limits and optional gzip persistence.
- [x] Adapt observation batch sizes from latency/RSS and stream very large JSON arrays with `ijson`.
- [x] Keep one persistent SQLite history writer, incremental refresh transactions and disk-backed normalized spooling.
- [x] Run the discovery service persistently with health/readiness/Prometheus endpoints and hardened systemd installation.
- [x] Add the original durable v1 distributed source-worker backend with leases, heartbeats, retry-safe task/batch IDs and one canonical history collector.
- [x] Replace the catalog dashboard from the ground up with Overview → Browse → Inspect → Compare, richer evidence context and responsive/safe rendering.

### Secure/automatic distributed phase

- [x] Integrate distributed submit/wait/streamed-collect directly into `llm-cluster-service` so recurring multi-node cycles are automatic.
- [x] Add generated worker/admin credentials, replay-protected HMAC worker identities, separate admin authorization, TLS and optional mTLS.
- [x] Add leader epochs so stale coordinators/leases cannot mutate task state after failover.
- [x] Store remote result batches as SHA-256 content-addressed artifacts and stream collection as NDJSON instead of materializing a complete cycle response.
- [x] Add worker capability advertisements, key/value locality labels, source affinity and bounded work stealing.
- [x] Feed CPU load, available RAM, Linux thermal readings and optional operator-supplied power/energy budgets into lease eligibility.
- [x] Add explicit worker drain/self-drain, cycle cancellation, failure quarantine and documented rolling-restart semantics.
- [x] Add live coordinator SQLite backup, offline atomic restore and active/standby leader-lease failover with epoch fencing while preserving one canonical history writer.
- [x] Add optional native OTLP/HTTP traces/counters through a `telemetry` extra while retaining Prometheus as the default dependency-light metrics path.
- [x] Add deterministic worker-crash/coordinator-restart/stale-epoch/backup fault tests plus authentication, capability, cancellation and duplicate-batch integration tests.
- [x] Add hardware-class synthetic runtime baselines alongside the broad generic CI performance gate; do not treat these as product LLM performance evidence.
- [x] Add shared SHA-256 source snapshots for normal full-body HTTP responses with explicit freshness-bounded replay; preserve low-memory streaming feeds without re-materialization.
- [x] Extend the systemd installer, discovery schema, docs and governance rules for secure distributed daemon operation.

## Highest priority — next distributed production-hardening phase

- [ ] Add external secret-manager integrations and zero-downtime worker/admin secret rotation; avoid long-lived static credentials where infrastructure supports stronger identity.
- [ ] Add automatic certificate enrollment/renewal/rotation and optional SPIFFE/SPIRE-style workload identity for mTLS deployments.
- [ ] Add an S3-compatible/object-store CAS backend with signed integrity manifests, retention policies and garbage collection independent of one shared filesystem.
- [ ] Add remote batch upload streaming/chunking for exceptionally large single batches; current v2 transport streams by bounded batch rather than one complete cycle.
- [ ] Add scheduler history/learning from source duration, failure rate, cache locality and worker energy cost rather than only current hard requirements + affinity.
- [ ] Add explicit worker maintenance windows, graceful coordinator handoff and rolling-upgrade compatibility negotiation by protocol/schema version.
- [ ] Add an external consensus/state backend option for deployments that need coordinators in separate storage/failure domains; do not fake quorum with SQLite replication.
- [ ] Add artifact integrity audit/scrub jobs, snapshot retention tiers and coordinator/CAS disaster-recovery drills.
- [ ] Add multi-hour/day chaos soak tests with repeated partitions, leader loss, clock skew, worker churn, disk pressure and duplicate/reordered delivery.
- [ ] Add cluster bootstrap/enrollment tooling that installs services, distributes CA material/worker credentials safely and verifies readiness across nodes.
- [ ] Collect real stable hardware-class runtime baselines from ThinkPads, mini PCs, SBCs and other actual workers before tightening class-specific regression floors.
- [ ] Correlate OTLP traces across daemon → coordinator → worker → source request → collector and surface trace IDs in operational diagnostics.

## Highest priority — dashboard/data UX next

- [ ] Add a live/staging dashboard mode that reads service status plus discovery output without mixing staging observations into canonical catalog truth.
- [ ] Add a Discovery/History view for current runs, source failures/circuit state, listing changes, disappear/reappear events and observation counts.
- [ ] Add per-product price-history timelines from `CatalogHistory` with explicit source/listing identity.
- [ ] Add authenticated distributed cycle/worker/drain/quarantine/leader-epoch status to the dashboard using secure read endpoints.
- [ ] Add model-fit and CAD landed-cost actions directly from the product inspector while preserving evidence/assumption warnings.
- [ ] Add exportable/importable named filter and comparison sets as JSON so research views can move between machines.
- [ ] Add measured-performance/range visualizations only when compatible sourced records exist; never graph spec arithmetic as measured throughput.
- [ ] Add user notes/tags and shortlist collections without modifying canonical product evidence fields.

## Highest priority — catalog/source work

- [ ] Add source-specific marketplace/API adapters where generic JSON/JSON-LD is insufficient (eBay, AliExpress/Alibaba exports, used-market feeds and retailer APIs).
- [ ] Add reviewed automatic promotion proposals from high-confidence discovery observations with human-readable diffs; never auto-promote unreviewed worker output.
- [ ] Add a pluggable live FX-rate provider while preserving explicit-rate/offline reproducibility.
- [ ] Backfill `max_memory_source_url`, dimensions, DC input and exact configuration evidence across legacy catalog records.
- [ ] Promote the highest-confidence discovery-watchlist targets after exact SKU, price and availability verification.
- [ ] Expand exact-SKU coverage for Ryzen 7840HS/8845HS/8945HS/HX370 systems, especially 64–128GB-capable bargains.
- [ ] Add more direct-China and used-market mobile boards, mini PCs, RK3588/RK3576 systems and unusual accelerators.

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
