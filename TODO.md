# TODO

## Completed in v0.5.0 — automated catalog intelligence

- [x] Build bounded asynchronous product/source adapters for current hardware discovery (`json` feeds and schema.org `Product` JSON-LD pages).
- [x] Replace thread-wrapped `urllib` with pooled native `aiohttp` networking and reusable keep-alive connections.
- [x] Add hierarchical bounded concurrency: source-agent workers, per-source URL subworkers, per-host HTTP limits, normalization workers and queue backpressure.
- [x] Keep meaningful network/filesystem/database/parse operations off the asyncio event loop.
- [x] Add a CI async-blocking guard for the end-to-end catalog refresh path.
- [x] Convert SQLite history to a persistent single-writer actor with WAL and batched `executemany` writes instead of schema/open/query churn per operation.
- [x] Run normalization and SQLite persistence concurrently after discovery.
- [x] Add runtime telemetry for total/discovery/persist+normalize time, per-source duration, request count, bytes and max in-flight HTTP work.
- [x] Add historical pricing plus title/currency/stock/listing disappearance and reappearance detection.
- [x] Add explicit-FX CAD conversion and Canada landed-cost planning with shipping, duty, brokerage and province tax assumptions.
- [x] Add seller/source confidence and exact-SKU configuration confidence.
- [x] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements from discovery observations.
- [x] Add board-level RAM evidence fields/source URLs and prevent CPU theoretical limits from being treated as board verification.
- [x] Add budget/high-memory/low-power/weird/EOL reports (`best_under_100`, `best_under_200`, `best_under_500`, etc.).
- [x] Add a self-contained catalog dashboard with comparison selection and browser-saved filters.
- [x] Add sourced vendor/community/local performance-record ingestion with model/runtime/workload/quantization/context provenance.
- [x] Add confidence-aware performance ranges that require at least two independent compatible measured sources.
- [x] Add safe model-family fit presets without converting model size into a throughput claim.
- [x] Track published power boundaries with explicit scope; processor TDP/cTDP is never labelled complete-node wall power.
- [x] Add generic third-party JSON/JSONL benchmark import mapping.
- [x] Keep specialist vision/audio/etc. records separate from LLM prefill/decode records.
- [x] Keep benchmarking optional; catalog releases do not require benchmark results.

## Highest priority — next efficiency/speed work

- [ ] Add conditional GET (`ETag`/`Last-Modified`) caching so unchanged product pages avoid body download and parsing.
- [ ] Add per-source retry/backoff/jitter and `Retry-After` handling with explicit rate-limit telemetry.
- [ ] Add adaptive concurrency that lowers or raises per-source workers from latency/error/rate-limit signals.
- [ ] Add a long-running scheduler/service mode that reuses HTTP/DNS pools across refresh cycles instead of recreating them per CLI invocation.
- [ ] Add benchmarkable end-to-end load fixtures (100/1,000/10,000 observations) and record throughput, peak RSS and event-loop lag in CI or an optional perf job.
- [ ] Profile JSON-LD parsing at large scale; add an optional process pool only if CPU parsing, rather than network latency, becomes the measured bottleneck.
- [ ] Add incremental/streaming normalization + persistence so very large sources do not require retaining every observation in memory before commit.
- [ ] Add source-specific adapters for marketplace APIs/exports where generic JSON or JSON-LD is insufficient.
- [ ] Add automatic promotion from high-confidence discovery observations into reviewed catalog fragments with a human-readable diff.
- [ ] Add a pluggable live FX-rate provider while preserving explicit-rate/offline reproducibility.

## Catalog accuracy — next

- [ ] Backfill `max_memory_source_url`, dimensions, DC input and exact configuration evidence across legacy catalog records.
- [ ] Promote the highest-confidence discovery-watchlist targets into `data/catalog/` after exact SKU, price and availability verification.
- [ ] Expand exact-SKU coverage for Ryzen 7840HS/8845HS/8945HS/HX370 systems, especially 64-128GB-capable bargains.
- [ ] Add more direct-China and used-market mobile boards, mini PCs, RK3588/RK3576 systems and unusual accelerators.
- [ ] Add exportable named dashboard filter sets (JSON) so saved views can be shared between machines rather than only browser-local storage.

## Evidence & estimates — next

- [ ] Ingest more independent real-world records for the same hardware/model/runtime signatures so confidence-aware ranges can graduate from single-source evidence.
- [ ] Add explicit provenance validators for runtime version, model artifact/hash, context length and quantization before records are considered range-compatible.
- [ ] Add result deduplication/fingerprints so mirrored benchmark posts do not count as independent sources.
- [ ] Import reproducible BC-250/RK3588/Jetson/Hailo/SOPHGO community results while keeping vendor and community evidence distinct.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.

## Optional benchmark tooling — maintenance

- [ ] Keep `llm-cluster-bench` adapters healthy as runtimes and output formats change.
- [ ] Add source-specific third-party benchmark import profiles on top of the generic importer.
- [ ] Add regression fixtures for every supported vendor/runtime adapter version.
