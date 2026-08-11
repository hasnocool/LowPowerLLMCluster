# Roadmap

## v0.1 — hardware planning foundation

- [x] machine-readable parts catalog
- [x] current Alibaba price/source snapshot
- [x] plain-language explanations and ASCII diagrams
- [x] transparent screening heuristic and BOM CLI
- [x] CI catalog validation

## v0.2 — heterogeneous hardware + governance

- [x] broaden scope to mini PCs, dev boards, SBCs, embedded and specialty boards
- [x] add BC-250, Jetson, RK3588 and mobile-CPU motherboard reference classes
- [x] project charter and guardrails
- [x] agent skills and workflow specs
- [x] mechanical release/document governance in CI
- [x] heterogeneous screening score that does not pretend core counts are cross-platform benchmarks

## v0.3 — accelerator expansion

- [x] NPU, TPU, AI ASIC, FPGA/adaptive-SoC and EOL accelerator categories
- [x] accelerator lifecycle, host, software-stack, LLM-support and power-scope metadata
- [x] honest unresolved-price support for secondary-market watches
- [x] GenAI accelerator references: Hailo-10H, SOPHGO BM1684X/BM1688, Tenstorrent Wormhole
- [x] specialist references: Coral Edge TPU and MemryX MX3
- [x] FPGA/adaptive research references: AMD Kria and Versal
- [x] decommissioned hardware references: Alveo V70 and Intel NCS2
- [x] accelerator-specific agent research skill and guardrails

## v0.4 — measured performance

- [x] benchmark profile, adapter-output and normalized result schemas
- [x] reproducible asynchronous llama.cpp runner with separate prefill/decode phases
- [x] normalized bridges for Hailo, SOPHGO, Tenstorrent and FPGA-native runtimes
- [x] specialist vision/audio/embedding benchmark path with workload-specific metrics
- [x] asynchronous external-meter power probe and manual-measured fallback
- [x] canonical complete-node power boundary for tokens/joule and units/joule
- [x] model hashing, fit screening, runtime-fit status and complete-system cost basis
- [x] tokens/joule and throughput-per-purchase-dollar calculations
- [x] comparison grouping that refuses to rank mismatched workloads/models together
- [x] stock-vs-modified experimental hardware identities through `configuration_id`
- [ ] persistent-runtime adapter for model-loaded idle and cleaner steady-state phase power
- [ ] real result collection across Ryzen, BC-250, RK3588/Jetson, Hailo/SOPHGO and FPGA hardware
- [ ] compare specialist-offload savings against always using general LLM nodes
- [ ] vendor model conversion/compile manifests and reproducibility capture

## v0.5 — sourcing automation

- [ ] seller/URL history
- [ ] price history and currency normalization
- [ ] availability/MOQ tracking
- [ ] duplicate-listing detection
- [ ] supplier confidence and landed-cost scoring
- [ ] asynchronous, rate-limited source adapters
- [ ] EOL/secondary-market watch thresholds

## v0.6 — cluster control plane

- [ ] node discovery and capability registry
- [ ] llama.cpp and accelerator-runtime lifecycle management
- [ ] workload-aware model/specialist placement
- [ ] queue-aware routing and automatic failover
- [ ] power-aware scheduling
- [ ] OpenAI-compatible gateway
- [ ] optional llama.cpp RPC orchestration for capacity-bound models

## v0.7 — dashboard

- [ ] web + CLI/TUI dashboards
- [ ] temperatures, power and model inventory
- [ ] prompt/decode throughput and tokens/joule
- [ ] hardware value and price-history views
- [ ] experimental/EOL hardware risk and software-health view
- [ ] accelerator utilization and offload-savings view
