# TODO

## v0.5 normalized optimizer — implemented

- [x] Add percentile-normalized heterogeneous AI hardware scoring.
- [x] Keep theoretical TOPS/TFLOPS separate from measured practical performance.
- [x] Add LLM speed, model-capacity, AI-compute, power-efficiency, cost-efficiency and off-grid dimensions.
- [x] Add workload profiles for interactive chat, coding agents, long context, always-on agents, off-grid AI and vision.
- [x] Add hard compatibility gates for model capacity, context, runtime, precision, power, energy and budget.
- [x] Add arithmetic tokens/joule, joules/token, tokens/kWh, energy/task, battery and solar-recovery metrics.
- [x] Add Pareto time/energy filtering.
- [x] Add multi-node aggregate and measured scaling-efficiency helpers.
- [x] Add software-support, deployability, reliability, sustained-performance, thermal-headroom and energy-proportionality dimensions.
- [x] Bridge benchmark-schema-v2 results into optimizer inputs while preserving complete-node power boundaries.
- [x] Add explainable ranking output and a dedicated `llm-cluster-optimize` CLI.

## Highest priority — catalog

- [ ] Build asynchronous product/source adapters for current hardware discovery.
- [ ] Add historical pricing and listing disappearance/change detection.
- [ ] Add CAD conversion and Canada landed-cost estimates.
- [ ] Add seller/source confidence and exact-SKU configuration confidence.
- [ ] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [ ] Verify board-level RAM maximums instead of relying on CPU theoretical limits.
- [ ] Add more direct-China and used-market mini PCs, mobile boards, SBCs and unusual accelerators.
- [ ] Add filters/reports: best under $100/$200/$500, high-memory bargains, low-power nodes, weird hardware, EOL bargains.

## Evidence & estimates

- [ ] Ingest sourced vendor/community performance records with model/runtime/workload provenance at scale.
- [ ] Add confidence-aware performance ranges only when multiple real sources justify them.
- [ ] Add model-family presets to the safe model-fit screen.
- [ ] Track published/estimated power boundaries without calling TDP complete-node watts.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.
- [ ] Import useful community BC-250/RK3588/Jetson/Hailo/SOPHGO results where reproducible.
- [ ] Populate normalized optimizer records for real Ryzen APU, RTX, Apple Silicon, Intel NPU, Coral TPU, BC-250 and Raspberry Pi accelerator systems.
- [ ] Add comparable-model benchmark cohorts so percentile populations never mix incompatible model/runtime workloads.

## Optimizer next steps

- [ ] Auto-generate normalized optimizer records from catalog + benchmark evidence instead of maintaining example records manually.
- [ ] Add historical score snapshots so percentiles can be reproduced after the comparison population changes.
- [ ] Add explicit cloud-provider candidates and local-vs-cloud fallback cost/energy policy.
- [ ] Add live battery/solar telemetry adapters for dynamic workload placement.
- [ ] Add scheduler integration that chooses local node, cluster, specialist accelerator or cloud fallback per request.
- [ ] Add measured network/PCIe/Thunderbolt interconnect penalties to distributed placement decisions.
- [ ] Add dashboard views for score dimensions, Pareto fronts, battery runtime and solar recovery.

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
