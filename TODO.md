# TODO

## Completed in v0.5.0 — automated catalog intelligence and E2E efficiency

- [x] Build bounded asynchronous product/source adapters for current hardware discovery (`json` feeds and schema.org `Product` JSON-LD pages).
- [x] Replace thread-wrapped `urllib` with pooled native `aiohttp` networking and reusable keep-alive/DNS connections.
- [x] Add hierarchical bounded concurrency: source-agent workers, per-source URL subworkers, per-host HTTP limits, normalization workers and queue backpressure.
- [x] Keep meaningful network/filesystem/database/parse operations off the asyncio event loop and enforce this with CI.
- [x] Convert SQLite history to a persistent single-writer actor with WAL and batched writes.
- [x] Add historical pricing plus title/currency/stock/listing disappearance and reappearance detection.
- [x] Add runtime telemetry for source duration, requests, bytes and max in-flight HTTP work.
- [x] Add conditional GET caching with `ETag` / `Last-Modified`; 304 responses reuse cached parsed observations without body download or reparsing.
- [x] Add bounded retry/backoff/jitter plus `Retry-After` handling and per-source rate-limit/retry telemetry.
- [x] Add adaptive per-source concurrency that multiplicatively backs off on errors/rate limits and cautiously increases after sustained healthy low-latency requests.
- [x] Add a long-running `llm-cluster-service` mode that reuses the HTTP connection pool, DNS cache, conditional cache and SQLite writer across refresh cycles.
- [x] Add incremental discovery batches, incremental SQLite persistence and an on-disk normalized-observation spool so full refreshes no longer require one in-memory observation list.
- [x] Add bounded streaming synchronous worker transforms (`map_sync_bounded_iter`) so transform inputs do not need to be materialized first.
- [x] Add 100/1,000/10,000 synthetic E2E load fixtures reporting observations/sec, peak RSS and event-loop lag.
- [x] Add a JSON-LD parser profiler. Synthetic 10k-product parsing is fast enough that a process pool is not justified yet; keep the thread/off-loop path until profiling proves otherwise.
- [x] Add explicit-FX CAD conversion and Canada landed-cost planning with shipping, duty, brokerage and province tax assumptions.
- [x] Add seller/source confidence and exact-SKU configuration confidence.
- [x] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [x] Add board-level RAM evidence fields/source URLs and prevent CPU theoretical limits from being treated as board verification.
- [x] Add budget/high-memory/low-power/weird/EOL reports and an interactive catalog dashboard.
- [x] Add sourced performance-record ingestion, confidence-aware ranges, safe model-fit presets and strict power-scope handling.

## Highest priority — next distributed/runtime work

- [ ] Add per-source circuit breakers so repeatedly failing/rate-limited sources cool down without consuming workers every cycle.
- [ ] Add cache TTL/pruning and optional compressed cache storage so long-running service mode cannot grow stale cache state indefinitely.
- [ ] Add adaptive batch sizing using observed normalization/SQLite latency and RSS instead of one fixed `stream_batch_size`.
- [ ] Add service health/readiness endpoints and Prometheus/OpenTelemetry-compatible runtime metrics.
- [ ] Add a systemd/service installer and restart policy for persistent discovery operation.
- [ ] Add a distributed worker backend so source agents can execute across multiple cluster nodes while retaining one canonical history/promotion coordinator.
- [ ] Add worker leases/heartbeats, idempotent batch IDs and retry-safe remote task resumption for distributed runs.
- [ ] Add optional per-adapter process isolation for unstable third-party parsers without forcing all parsing into processes.
- [ ] Add CI performance regression thresholds from the synthetic 1k/10k fixtures without making timing-sensitive checks flaky on shared runners.
- [ ] Add streaming JSON parsing (`ijson` or equivalent) for exceptionally large JSON feeds so the downloaded decoded JSON document itself need not be fully materialized.

## Highest priority — next catalog/source work

- [ ] Add source-specific adapters for marketplace APIs/exports where generic JSON or JSON-LD is insufficient (eBay, AliExpress/Alibaba exports, used-market feeds, retailer APIs).
- [ ] Add automatic promotion from high-confidence discovery observations into reviewed catalog fragments with a human-readable diff.
- [ ] Add a pluggable live FX-rate provider while preserving explicit-rate/offline reproducibility.
- [ ] Backfill `max_memory_source_url`, dimensions, DC input and exact configuration evidence across legacy catalog records.
- [ ] Promote the highest-confidence discovery-watchlist targets into `data/catalog/` after exact SKU, price and availability verification.
- [ ] Expand exact-SKU coverage for Ryzen 7840HS/8845HS/8945HS/HX370 systems, especially 64-128GB-capable bargains.
- [ ] Add more direct-China and used-market mobile boards, mini PCs, RK3588/RK3576 systems and unusual accelerators.
- [ ] Add exportable named dashboard filter sets (JSON) so saved views can be shared between machines.

## Evidence & estimates — next

- [ ] Ingest more independent real-world records for the same hardware/model/runtime signatures.
- [ ] Add explicit provenance validators for runtime version, model artifact/hash, context length and quantization before records are range-compatible.
- [ ] Add result deduplication/fingerprints so mirrored benchmark posts do not count as independent sources.
- [ ] Import reproducible BC-250/RK3588/Jetson/Hailo/SOPHGO community results while keeping vendor and community evidence distinct.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.

## Optional benchmark tooling — maintenance

- [ ] Keep `llm-cluster-bench` adapters healthy as runtimes and output formats change.
- [ ] Add source-specific third-party benchmark import profiles on top of the generic importer.
- [ ] Add regression fixtures for every supported vendor/runtime adapter version.
