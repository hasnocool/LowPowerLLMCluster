# TODO

## Completed in v0.5.0 — automated catalog intelligence

- [x] Build bounded asynchronous product/source adapters for current hardware discovery (`json` feeds and schema.org `Product` JSON-LD pages).
- [x] Keep blocking HTTP and SQLite work off the event loop with bounded worker-thread I/O and per-thread SQLite connections.
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
- [x] Add a current discovery watchlist for 7840HS/8945HS, RK3576/RK3588, unusually large-memory edge systems and used Alveo-class hardware.

## Highest priority — next catalog work

- [ ] Add source-specific adapters for marketplace APIs/exports where generic JSON or JSON-LD is insufficient (eBay, AliExpress/Alibaba exports, used-market feeds, retailer APIs).
- [ ] Add a scheduler/service command for periodic discovery refreshes, retention and notification hooks without making CI depend on live marketplaces.
- [ ] Add automatic merge/promotion from high-confidence discovery observations into reviewed catalog fragments with a human-readable diff.
- [ ] Add a pluggable live FX-rate provider while preserving the current explicit-rate/offline mode for reproducibility.
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

## Hardware discovery — next

- [ ] Verify current prices/availability for the discovery watchlist and score promotion readiness.
- [ ] Find cheap high-capacity DDR5/LPDDR systems with board-verified 96GB/128GB+ support.
- [ ] Add more current GenAI NPUs/TPUs/ASICs only when a real transformer runtime and memory boundary are documented.
- [ ] Track used/decommissioned Alveo, edge-inference and large-memory accelerator listings with current price history.
- [ ] Continue console-derived / specialty APU research only where Linux/runtime support is practically usable.

## Optional benchmark tooling — maintenance

- [ ] Keep `llm-cluster-bench` adapters healthy as runtimes and output formats change.
- [ ] Add source-specific third-party benchmark import profiles on top of the generic importer.
- [ ] Add regression fixtures for every supported vendor/runtime adapter version.
