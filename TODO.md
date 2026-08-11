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
- [x] Add exact-hardware RK1/RK3588, Jetson Orin Nano Super and stock BC-250 benchmark evidence.
- [x] Add source health history and consecutive-failure tracking.
- [x] Add transient HTTP retry/backoff with jitter and Retry-After handling.
- [x] Add stale-listing warnings without deleting historical observations.
- [x] Add named daily/weekly autonomous discovery profiles.
- [x] Add scheduled GitHub refresh with automatic FX and current-market report regeneration.
- [x] Add configurable watchlists with per-watch price/landed-cost/benchmark thresholds.
- [x] Add significant price-drop, stock-return and new-product alerts.
- [x] Add benchmark regression/improvement detection for compatible exact-hardware signatures.
- [x] Add source query/run budgets with persisted daily estimated request usage.
- [x] Add compact generated daily change-intelligence reports.
- [x] Make discrete GPUs a first-class `gpu_accelerator` sourcing category.
- [x] Seed current/used GPU references across NVIDIA CUDA, AMD ROCm/Vulkan and Intel oneAPI/SYCL ecosystems.
- [x] Add GPU queries to daily/weekly autonomous sourcing profiles and a dedicated GPU-value watchlist.
- [x] Add decision-quality scoring from price history, model fit, confidence, freshness and volatility.
- [x] Add native-currency new-all-time-low detection.
- [x] Add price trend and volatility metrics.
- [x] Add opportunity freshness/expiry semantics.
- [x] Add P1-P4 alert prioritization.
- [x] Add ranked Buy / Watch / Ignore / Experimental daily recommendations.
- [x] Add complete-node TCO with explicit GPU + CPU/host + motherboard + RAM + storage + PSU + PCIe/OCuLink/riser + cooling + chassis + electricity scenarios.
- [x] Re-rank daily recommendations using complete-node acquisition and operating cost rather than card/component sticker price alone.
- [x] Add editable light/mixed/always-on/high-electricity TCO scenarios and `daily-tco` reports.
- [x] Add break-even analysis for product price, electricity rate and daily load hours between two complete-node options.
- [x] Add ownership-aware TCO profiles for new build, reuse host core, reuse complete host and reuse everything.
- [x] Allow custom already-owned component overrides and keep owned hardware in operating-power calculations.
- [x] Make break-even comparisons accept different ownership profiles for each option.
- [ ] Replace generic TCO component assumptions with sourced component/BOM observations per exact deployment when evidence is available.
- [ ] Add compatibility validation for owned hosts: PCIe generation/lanes, physical slots, PSU connectors/headroom, chassis clearance and cooling capacity.
- [ ] Add province presets plus tariff/HS-code evidence without pretending customs treatment is universal.
- [ ] Persist historical landed-CAD snapshots so pure FX movement can be compared without recomputing old observations at current FX.
- [ ] Add provider-reported remaining quota/reset timestamps when APIs expose them.
- [ ] Add notification delivery adapters for email/webhook/chat after alert evidence is generated.
- [ ] Add more structured used-market sources where official/legal API access exists.
- [ ] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [ ] Verify board-level RAM maximums instead of relying on CPU theoretical limits.
- [ ] Add more direct-China and used-market mini PCs, mobile boards, SBCs, GPUs and unusual accelerators.

## GPU coverage

- [x] Track RTX 5060 Ti 16GB, RTX 3090 24GB, RX 9070/9070 XT 16GB, Arc B580 12GB and Arc A770 16GB reference products.
- [x] Count CPU/host, motherboard, RAM, storage, PSU, PCIe integration, cooling, chassis and board-power-derived operating scenarios in GPU TCO comparisons.
- [x] Add GPU-vs-integrated-node break-even analysis using complete-node TCO rather than card sticker price.
- [x] Add ownership-aware GPU acquisition so existing compatible host parts are not purchased twice.
- [ ] Expand NVIDIA coverage to other 12GB/16GB/24GB/32GB cards when live pricing justifies catalog inclusion.
- [ ] Expand AMD coverage to additional maintained ROCm/Vulkan cards with useful VRAM-per-dollar.
- [ ] Expand Intel Arc coverage as current/used pricing changes.
- [ ] Add workstation/datacenter GPU watches when used prices cross practical local-LLM thresholds.
- [ ] Ingest exact-GPU llama.cpp/vLLM/MLC/community measurements only when board/runtime/model provenance is sufficient.
- [ ] Add used-GPU condition signals such as board-partner SKU, cooler/fan notes, return policy and seller history where the source provides them.

## Evidence & estimates

- [x] Ingest sourced vendor/community performance records with model/runtime/workload provenance.
- [x] Keep compatible measurements grouped by exact benchmark signature instead of averaging unlike runs.
- [x] Add exact-product Jetson and stock BC-250 community/vendor measurements without copying them to similar hardware.
- [x] Preserve TGP/TBP/board-power evidence separately while using it only as an explicitly low-confidence complete-node TCO planning input.
- [ ] Add confidence-aware performance ranges only when multiple independent compatible real sources justify them.
- [ ] Add model-family presets beyond the default transparent Q4 decision-capacity screen.
- [ ] Benchmark the ThinkPad L14 as an optional local reference/calibration node.
- [ ] Import additional useful BC-250/RK3588/Jetson/Hailo/SOPHGO/GPU results only when exact hardware/runtime provenance is available.

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
- [ ] Do not make benchmarking a prerequisite for catalog releases or daily recommendations.
