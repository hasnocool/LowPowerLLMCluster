# TODO

## Highest priority — catalog / market intelligence

- [x] Build asynchronous product/source adapter contract for current hardware discovery.
- [x] Add append-only historical pricing with listing/source identity.
- [x] Add CAD conversion input and Canada landed-cost estimator.
- [x] Add exact-SKU/configuration confidence.
- [x] Add sourced vendor/community performance ingestion with model/runtime/workload provenance.
- [x] Add live manufacturer/distributor/structured-marketplace adapters where terms/API access permit.
- [x] Add listing disappearance/reappearance and stock-state observations.
- [x] Add automatic sourced CAD FX refresh and historical FX snapshots.
- [x] Add seller/source reputation confidence separately from SKU confidence.
- [x] Add compatibility-preserving benchmark aggregation.
- [x] Add CAD buying reports: under CA$100/250/500, 32GB+, low-power, weird-hardware, EOL, measured-evidence.
- [x] Add exact-hardware RK1/RK3588, Jetson Orin Nano Super and stock BC-250 benchmark evidence.
- [x] Add source health history and consecutive-failure tracking.
- [x] Add transient HTTP retry/backoff with jitter and Retry-After handling.
- [x] Add stale-listing warnings without deleting historical data.
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
- [x] Fetch live BOM product/cost data for CPU, motherboard, RAM, storage, PSU, PCIe/OCuLink, cooling and chassis using structured online sources.
- [x] Persist current BOM selections and append-only landed-CAD BOM price history.
- [x] Overlay selected sourced BOM costs into TCO one component at a time while preserving fallback assumption provenance.
- [x] Add cross-component compatibility resolution for CPU socket, RAM generation, PCIe slot/lanes, PSU wattage/connectors, motherboard/chassis form factor, GPU clearance and cooler dimensions.
- [x] Generate per-GPU cheapest compatible/provisionally-compatible complete builds from live BOM candidates and recent GPU market evidence.
- [x] Preserve unresolved exact board-partner dimensions/connectors as provisional compatibility instead of assuming they fit.
- [x] Add exact-SKU manufacturer specification association/fetching with identity verification and field-level provenance.
- [x] Enrich motherboard lane/M.2 facts, PSU connectors, chassis clearances and exact/reference GPU board requirements before compatibility solving.
- [x] Allow exact GPU board facts to promote provisional builds or reject physically/electrically invalid combinations.
- [x] Persist manufacturer spec evidence and expose `spec-config` / `spec-evidence` CLI views.
- [x] Preserve manufacturer + MPN identity from structured distributor/manufacturer listings for enrichment.
- [x] Add automatic official-manufacturer association discovery using manufacturer registry, official search/sitemap candidates and conservative MPN/model identity scoring.
- [x] Cache verified/not-verified manufacturer associations with expiry so exact-SKU coverage grows across refreshes without repeated discovery work.
- [x] Add conservative automatic compatibility-field parsing for CPU, motherboard, PSU, chassis, cooler and exact GPU manufacturer pages.
- [x] Expose manufacturer discovery configuration and cached associations through CLI views.
- [x] Parse schema.org `Product.additionalProperty` and real HTML specification tables before flattened-page regex fallback.
- [x] Parse motherboard CPU/BIOS support matrices when a target CPU row is available.
- [x] Follow bounded same-manufacturer manual/datasheet/spec PDF links and text-extract compatibility evidence with field-level provenance.
- [x] Preserve complete parsed CPU/BIOS support rows on motherboard candidates for later CPU+motherboard pair evaluation.
- [x] Evaluate motherboard + CPU BIOS compatibility after build pairing, rejecting explicit unsupported rows and retaining minimum BIOS requirements/warnings.
- [x] Keep absence from incomplete/paginated support matrices provisional rather than treating it as unsupported.
- [x] Discover and rank linked official manufacturer CPU-support, BIOS and download endpoints from verified motherboard pages.
- [x] Capture BIOS Flashback / CPU-less firmware-update evidence and expose an evidence-based boot-readiness score on complete builds.
- [x] Ingest linked official paginated/API-backed CPU-support matrices and prove completeness only from explicit pagination metadata.
- [x] Discover separate manufacturer CPU-support/download endpoints when they are not linked from the verified product page.
- [x] Add conservative vendor-specific BIOS comparators for MSI, Gigabyte/AORUS, ASUS and same-series ASRock releases.
- [x] Preserve revision-scoped BIOS history when official manufacturer API payloads expose board/PCB revision metadata.
- [x] Automatically extract seller-stated PCB revision and currently installed BIOS/UEFI as lower-confidence marketplace evidence.
- [x] Automatically enrich listings with SSD controller/NAND/interface, GPU board/VBIOS, RAM topology, mobile SKU/SoC and accelerator host-context facts when explicitly present.
- [x] Ingest the same narrow identity fields from structured JSON-LD additional properties, distributor parameter/spec arrays, marketplace aspects and manufacturer spec tables.
- [x] Feed marketplace short descriptions through the lower-priority identity parser when the source API exposes them.
- [x] Persist revision-scoped manufacturer BIOS API history in motherboard structured evidence.
- [x] Correlate seller-stated PCB revision + installed BIOS with the selected CPU minimum and official revision-scoped history without upgrading seller evidence to manufacturer authority.
- [x] Add an auditable sourced-power measurement feed with exact hardware identity, HTTPS provenance and explicit power boundaries.
- [x] Seed measured power evidence across exact Apple M1/M4 configurations, a Ryzen 7840HS mini PC, Pixel 10 Pro XL, Galaxy S26 Ultra and an RTX 3090 board-only sample.
- [x] Add a data-driven vendor parameter alias registry so new structured source labels can map into normalized identity fields without inventing values.
- [x] Add a conservative factory-firmware rule registry that permits serial/batch/revision/physical-label mappings only when a vendor publishes the relationship.
- [x] Preserve ASRock's documented BIOS-chip sticker method as verified factory/default BIOS evidence.
- [x] Add promotion-aware discovery with persisted Held/promotion-ready/canonical decisions and exact-listing canonical provenance.
- [x] Add bounded Held-record official-product/schema.org enrichment before promotion re-evaluation.
- [x] Apply source-quality cadence and crawl-budget adaptation to curated public sources as well as learned sources.
- [x] Add typed persistent source-failure cooldowns with a restart-safe scheduler epoch.
- [x] Compact only payload-identical SQLite discovery heartbeats while preserving provenance-bearing payload changes and keeping `listing_state` fresh.
- [x] Add source-health and promotion-health dashboard APIs, complete-population pagination and stale-promotion watchdogs.
- [ ] Continuously harvest exact complete-node/device power measurements across Apple, mini PCs/SBCs, phones/tablets and unusual accelerators.
- [ ] Harvest exact GPU + host wall-input measurements under llama.cpp/vLLM/MLC workloads with host CPU/motherboard/RAM/PSU identity.
- [ ] Harvest exact SSD idle/average/max power with controller + NAND + capacity identity from auditable numeric sources.
- [ ] Harvest incremental RAM-topology power evidence where test methodology isolates DIMM configuration.
- [ ] Expand vendor parameter aliases only as real manufacturer/distributor schemas expose new labels.
- [ ] Populate serial/manufacture-batch/revision → factory BIOS rules only where vendors publish a verifiable mapping; do not reverse-engineer undocumented serial formats.
- [ ] Expand the manufacturer registry and stable manufacturer search-page templates as live sourcing encounters new brands.
- [x] Infer likely shipped BIOS/hardware revision only when manufacturer or seller evidence supports it.
- [x] Add compatibility validation for owned hosts: PCIe generation/lanes, physical slots, PSU connectors/headroom, chassis clearance and cooling capacity.
- [x] Add province presets plus tariff/HS-code evidence without pretending customs treatment is universal.
- [x] Persist historical landed-CAD snapshots so pure FX movement can be compared without recomputing old observations at current FX.
- [x] Add provider-reported remaining quota/reset timestamps when APIs expose them.
- [x] Add notification delivery adapters for email/webhook/chat after alert evidence is generated.
- [ ] Add more structured used-market sources where official/legal API access exists.
- [x] Normalize form factor, dimensions, DC input, PSU/cooling and host requirements.
- [x] Verify board-level RAM maximums instead of relying on CPU theoretical limits.
- [ ] Add more direct-China and used-market mini PCs, mobile boards, SBCs, GPUs and unusual accelerators.

## Apple and mobile coverage

- [x] Add first-class `apple_silicon_system`, `mobile_phone`, `tablet` and `media_device` catalog categories.
- [x] Cover Apple-silicon Macs from M1 through current M5/M5 Pro/M5 Max generations, including MacBook Air/Pro, Mac mini, iMac and Mac Studio.
- [x] Add iPad Pro M1/M2/M4/M5, current iPad Air M4, current iPhone A19/A19 Pro family references and Apple TV 4K A15.
- [x] Add current Android low-power reference phones including Pixel 10 Pro 16GB and Galaxy S26 Ultra 12/16GB.
- [x] Add mobile runtime classes so macOS Apple-silicon systems can be general-purpose nodes while iOS/iPadOS/tvOS/Android devices retain sandbox, service and thermal constraints.
- [x] Add conservative mobile/unified-memory capacity reserves without deriving throughput from SoC marketing specifications.
- [x] Add Apple/mobile discovery queries to daily and weekly market refresh profiles.
- [x] Keep battery capacity, charger wattage and charging rate separate from measured inference wall-input power.
- [x] Resolve Apple marketplace listings into explicit A-number/model/part identity, chip, RAM, SSD, screen and explicitly stated CPU/GPU core counts without inferring missing bins.
- [x] Carry used-Mac battery health/cycles plus stated Activation Lock and MDM evidence separately from exact SKU identity.
- [x] Feed resolved Apple configuration through existing live price/shipping, sourced CAD FX and landed-cost/TCO evidence paths.
- [x] Extract explicit mobile model/SKU, SoC and SoC-variant identity from listings/spec text and structured source fields when present.
- [x] Seed complete-device measured power for exact M1 Max, M4/M4 Pro, M4 Max, Pixel 10 Pro XL and Galaxy S26 Ultra configurations.
- [ ] Expand the Apple A-number/model/part-number knowledge base and add authoritative order-number mappings for more generations/regions.
- [ ] Ingest LLM-specific complete-node Apple idle/load/inference power with exact model/runtime/workload provenance.
- [x] Add used-Mac warranty/AppleCare and seller return-policy evidence where sources expose them.
- [ ] Expand Android phone/tablet coverage based on RAM, runtime support and used-market value.

## GPU coverage

- [x] Track RTX 5060 Ti 16GB, RTX 3090 24GB, RX 9070/9070 XT 16GB, Arc B580 12GB and Arc A770 16GB reference products.
- [x] Count CPU/host, motherboard, RAM, storage, PSU, PCIe integration, cooling, chassis and board-power-derived operating scenarios in GPU TCO comparisons.
- [x] Add GPU-vs-integrated-node break-even analysis using complete-node TCO rather than card sticker price.
- [x] Add ownership-aware GPU acquisition so existing compatible host parts are not purchased twice.
- [x] Feed current sourced host/BOM product costs into GPU complete-node TCO where online listings pass confidence/compatibility filters.
- [x] Solve cheapest complete host builds per tracked GPU while rejecting known socket/memory/power/clearance incompatibilities.
- [x] Add exact/reference-board enrichment for RTX 3090 Founders Edition and Intel Arc B580 Limited Edition without transferring those dimensions to arbitrary partner cards.
- [x] Allow board-partner GPU MPNs to discover official manufacturer pages automatically when the manufacturer registry can verify them.
- [x] Prefer structured GPU properties/spec tables/manual fields over flattened manufacturer-page prose for dimensions, connectors and PSU requirements.
- [x] Extract explicit GPU board partner, PCB/board revision and VBIOS identity from listing/spec text and structured source fields when present.
- [x] Seed board-only measured power for MSI RTX 3090 Gaming X Trio while preserving accelerator-board scope.
- [ ] Expand NVIDIA coverage to other 12GB/16GB/24GB/32GB cards when live pricing justifies catalog inclusion.
- [ ] Expand AMD coverage to additional maintained ROCm/Vulkan cards with useful VRAM-per-dollar.
- [ ] Expand Intel Arc coverage as current/used pricing changes.
- [ ] Add workstation/datacenter GPU watches when used prices cross practical local-LLM thresholds.
- [ ] Ingest exact-GPU llama.cpp/vLLM/MLC/community measurements only when board/runtime/model provenance is sufficient.
- [x] Add used-GPU condition signals such as board-partner SKU, cooler/fan notes, return policy and seller history where the source provides them.

## Evidence & estimates

- [x] Ingest sourced vendor/community performance records with model/runtime/workload provenance.
- [x] Keep compatible measurements grouped by exact benchmark signature instead of averaging unlike runs.
- [x] Add exact-product Jetson and stock BC-250 community/vendor measurements without copying them to similar hardware.
- [x] Preserve TGP/TBP/board-power evidence separately while using it only as an explicitly low-confidence complete-node TCO planning input.
- [x] Preserve manufacturer compatibility evidence field-by-field with source URL, timestamp, extraction method and association identity.
- [x] Preserve automatic association identity score/cache state separately from extracted compatibility evidence.
- [x] Preserve structured-source class (`additionalProperty`, HTML table, CPU/BIOS matrix, PDF) on each extracted manufacturer fact.
- [x] Preserve pair-level CPU/BIOS manufacturer support provenance in compatible-build results.
- [x] Preserve boot-readiness as a firmware/installability signal rather than a performance metric.
- [x] Feed explicit SSD controller/NAND/interface, RAM topology, GPU board/VBIOS/host context and mobile SKU/SoC identity into adaptive power matching.
- [x] Allow verified structured manufacturer identity facts to narrow adaptive power identities without replacing stronger direct measurements.
- [x] Add `docs/EVIDENCE_HARVESTING.md` with measurement-boundary and per-category harvesting rules.
- [x] Add confidence-aware performance ranges only when multiple independent compatible real sources justify them.
- [x] Add model-family presets beyond the default transparent Q4 decision-capacity screen.
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
- [x] Add importers for third-party benchmark records.
- [x] Keep specialist vision/audio metrics separate from LLM throughput.
- [x] Do not make benchmarking a prerequisite for catalog releases or daily recommendations.
