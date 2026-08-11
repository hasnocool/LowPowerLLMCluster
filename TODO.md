# TODO

## Highest priority — catalog / market intelligence

- [x] Build asynchronous product/source adapter contract for current hardware discovery.
- [x] Add append-only historical pricing with listing/source identity.
- [x] Add CAD conversion input and Canada landed-cost estimator.
- [x] Add exact-SKU/configuration confidence.
- [x] Add sourced vendor/community performance ingestion with model/runtime/workload provenance.
- [x] Add live source adapters: public manufacturer JSON-LD, Mouser, DigiKey and eBay Browse.
- [x] Add listing disappearance/reappearance observations with query-scope protection.
- [x] Add automatic sourced FX refresh and historical FX snapshots using Bank of Canada Valet.
- [x] Add seller/source reputation confidence separately from SKU confidence.
- [x] Add compatible benchmark aggregation without mixing different model/runtime/workload signatures.
- [ ] Add live stock/availability normalization across source-specific vocabularies.
- [ ] Add province presets plus tariff/HS-code evidence without pretending customs treatment is universal.
- [ ] Add automatic credential/token refresh for DigiKey instead of requiring an externally obtained access token.
- [ ] Add more manufacturer/distributor source seeds and source-specific parsing fixtures.
- [ ] Add seller/source reputation history rather than only observation-time confidence.
- [ ] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [ ] Verify board-level RAM maximums instead of relying on CPU theoretical limits.
- [ ] Add more direct-China and used-market mini PCs, mobile boards, SBCs and unusual accelerators.
- [ ] Add filters/reports: best under $100/$200/$500, high-memory bargains, low-power nodes, weird hardware, EOL bargains.

## Evidence & estimates

- [x] Ingest sourced vendor/community performance records with model/runtime/workload provenance.
- [x] Aggregate compatible measured records into count/median/range/mean/confidence groups.
- [ ] Add confidence-aware performance ranges to product views only when multiple compatible real sources justify them.
- [ ] Add model-family presets to the safe model-fit screen.
- [ ] Track published/estimated power boundaries without calling TDP complete-node watts.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.
- [ ] Import useful community BC-250/RK3588/Jetson/Hailo/SOPHGO results where reproducible.

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
