# TODO

## Highest priority — catalog / market intelligence

- [x] Build asynchronous product/source adapter contract for current hardware discovery.
- [x] Add append-only historical pricing with listing/source identity.
- [x] Add CAD conversion input and Canada landed-cost estimator.
- [x] Add exact-SKU/configuration confidence.
- [x] Add sourced vendor/community performance ingestion with model/runtime/workload provenance.
- [x] Add live manufacturer/distributor/structured-marketplace adapters where terms/API access permit.
- [x] Add listing disappearance/reappearance and stock-state observations.
- [x] Add automatic sourced FX refresh and historical FX snapshots.
- [x] Add seller/source reputation confidence separately from SKU confidence.
- [x] Add compatibility-preserving benchmark aggregation.
- [x] Add CAD buying reports: under CA$100/250/500, 32GB+, low-power, weird-hardware, EOL, measured-evidence.
- [x] Add an exact-hardware benchmark reference product and seed sourced RK1/RK3588 llama.cpp evidence.
- [x] Add source health history and consecutive-failure tracking.
- [x] Add transient HTTP retry/backoff with jitter and Retry-After handling.
- [x] Add stale-listing warnings without deleting historical observations.
- [x] Add named daily/weekly autonomous discovery profiles.
- [x] Add scheduled GitHub refresh with automatic FX and current-market report regeneration.
- [x] Add additional exact-hardware Jetson Orin Nano Super community/vendor benchmark evidence.
- [ ] Add province presets plus tariff/HS-code evidence without pretending customs treatment is universal.
- [ ] Add source-specific rate-limit budget telemetry and next-allowed-request timestamps.
- [ ] Add alert thresholds for repeated source failures, newly stale listings, and major price changes.
- [ ] Add more structured used-market sources where official/legal API access exists.
- [ ] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [ ] Verify board-level RAM maximums instead of relying on CPU theoretical limits.
- [ ] Add more direct-China and used-market mini PCs, mobile boards, SBCs and unusual accelerators.

## Evidence & estimates

- [x] Ingest sourced vendor/community performance records with model/runtime/workload provenance.
- [x] Keep compatible measurements grouped by exact benchmark signature instead of averaging unlike runs.
- [x] Add additional exact-product Jetson community/vendor measurements without copying them to other Orin products.
- [ ] Add confidence-aware performance ranges only when multiple independent compatible real sources justify them.
- [ ] Add model-family presets to the safe model-fit screen.
- [ ] Track published/estimated power boundaries without calling TDP complete-node watts.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.
- [ ] Import additional useful BC-250/RK3588/Jetson/Hailo/SOPHGO results only when exact hardware/runtime provenance is available.

## Hardware discovery

- [ ] More Ryzen 7840HS/8845HS/8945HS/HX370 bareboards and mini PCs.
- [ ] Cheap high-capacity DDR5/LPDDR systems.
- [ ] More RK3588/RK3576-class 16-32GB systems.
- [ ] Current GenAI NPUs/TPUs/ASICs with real transformer runtimes.
- [ ] Used/decommissioned Alveo, edge inference cards and other large-memory accelerators.
- [ ] Console-derived / specialty APUs where software is usable.

## Optional benchmark tooling

- [ ] Keep `llm-cluster-bench` adapters healthy as runtimes change.
- [ ] Add importers for third-party benchmark records.
- [ ] Keep specialist vision/audio metrics separate from LLM throughput.
- [ ] Do not make benchmarking a prerequisite for catalog releases.
