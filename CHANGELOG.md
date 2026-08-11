# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-08-10

### Added

- Asynchronous product-discovery adapter contract plus deterministic JSON feed importer.
- Live manufacturer JSON-LD discovery for public schema.org `Product` / `Offer` pages.
- Mouser Search API adapter using `MOUSER_API_KEY`.
- DigiKey Product Information V4 adapter using external OAuth credentials with CA/CAD locale defaults.
- eBay Browse API adapter using application OAuth and the Canadian marketplace for used/secondary-market discovery.
- Credential-free source configuration in `data/market/sources.json`; secrets remain environment-only.
- Normalized listing model and concurrent multi-source discovery with source/listing deduplication and per-source success/failure status.
- Append-only price observation history linked back to catalog part IDs.
- Exact-SKU/configuration confidence scoring that does not confuse CPU theoretical RAM limits with installed RAM.
- Independent seller/source confidence using source class plus marketplace feedback signals when available.
- Query-scope-aware `discovered`, `disappeared`, and `reappeared` listing lifecycle tracking.
- Automatic sourced CAD FX snapshots from the Bank of Canada Valet API with append-only FX history.
- Explicit Canadian landed-cost breakdown for item, shipping, duty, brokerage and tax.
- Sourced vendor/community performance ingestion requiring model, runtime, workload, metric, unit and source URL provenance.
- Strict compatible-performance aggregation that keeps different model variants, quantizations, runtime versions, workload phases, units, context dimensions and hardware configurations separate.
- Turing RK1 32GB catalog reference with exact-product, vendor-published llama.cpp Q4_K_M benchmark evidence for 1.5B, 3B and 7B models.
- Exact-hardware Jetson Orin Nano Super community llama.cpp/CUDA evidence plus NVIDIA MLC INT4 reference measurements kept in separate compatibility groups.
- CAD buying reports for under CA$100, CA$250 and CA$500, 32GB+, low-power, weird-hardware, EOL and measured-evidence candidates.
- Broader official manufacturer/source seed registry, including Turing Pi, Radxa/ALLNET and Orange Pi references.
- Source-health history with last-success/failure state, result counts and consecutive-failure tracking.
- Exponential retry/backoff with jitter and numeric `Retry-After` handling for transient network, 429 and common 5xx failures.
- Stale-listing warnings based on last successful observation without deleting historical data or claiming the listing is gone.
- Named `daily-market` and `weekly-deep-scan` autonomous refresh profiles.
- `llm-cluster-refresh` CLI for profile execution, health inspection, stale warnings and report regeneration.
- Scheduled GitHub Actions refresh that can use optional marketplace secrets, refresh Bank of Canada FX, regenerate current reports and commit changed evidence.
- `docs/AUTONOMOUS_REFRESH.md` operational guide.
- `llm-cluster-market` CLI with `discover`, `history`, `landed`, `refresh-fx`, `ingest-performance`, `aggregate-performance`, and `report` workflows.
- `specs/MARKET_INTELLIGENCE.md` and tests for matching, history deduplication, seller confidence, lifecycle tracking, landed-cost math, evidence ingestion, compatible aggregation, JSON-LD normalization, CAD report behavior, retry policy and stale detection.

### Changed

- Live market I/O uses `httpx.AsyncClient`; blocking filesystem work is isolated from the event loop.
- Failed or credential-disabled sources cannot generate false listing-disappearance events.
- v0.5 keeps the catalog authoritative while listings, prices, FX rates, seller reputation and benchmark records remain time-stamped evidence layers.
- Benchmark evidence stays attached to the exact tested product/configuration instead of being copied across boards that merely share a SoC.
- CAD reports prefer active live listing observations and fall back to clearly labeled catalog midpoint pricing only when sourced FX is available.
- Community energy-efficiency evidence preserves its published measurement boundary; internal Jetson rail telemetry is not relabeled as complete-node wall-input power.

## [0.4.1] - 2026-08-10

### Changed

- Re-centered the project on its original purpose: product catalog, sourcing, pricing, compatibility and buying decisions.
- Demoted the v0.4 benchmark harness to optional evidence tooling; physical hardware ownership is not required for catalog inclusion.
- Reframed `llm-cluster rank` as a catalog/buying shortlist rather than pseudo-performance ranking.
- Corrected memory semantics so barebones no longer appear to include the CPU's theoretical maximum RAM.

### Added

- Explicit performance provenance vocabulary: local/community/vendor measured, derived/spec-based estimate, or unknown.
- `specs/EVIDENCE.md` with confidence and estimation guardrails.
- `llm-cluster list` filtering by category, budget and memory.
- `llm-cluster show` for product/evidence inspection.
- `llm-cluster fit` for conservative model-weight capacity screening without predicting tokens/sec.
- Separate `max_memory_gb` / `memory_config_status` semantics and memory-evidence weighting.

## [0.4.0] - 2026-08-10

### Added

- Measured-performance benchmark harness with a dedicated `llm-cluster-bench` CLI.
- Native asynchronous `llama-bench` JSON adapter with separate prefill and decode benchmark phases.
- Normalized vendor-runtime JSON bridges for Hailo, SOPHGO LLM-TPU, Tenstorrent TT-Metal and FPGA-native/Vitis-style experiments.
- Workload-specific specialist benchmark path for vision, audio, embeddings and other non-LLM accelerators.
- Benchmark profile, vendor adapter-output and measured-result JSON schemas.
- Asynchronous power sampling through external meter commands plus explicitly manual measured-power input.
- Power-boundary guardrail: canonical tokens/joule and specialist units/joule require `complete_node_input` scope.
- Model artifact hashing, file-size fit screening and separate runtime-verified fit status.
- Complete-system acquisition-cost handling and throughput-per-purchase-dollar metrics.
- Result comparison that groups incompatible model/workload signatures instead of ranking them together.
- Example benchmark profiles for llama.cpp CPU/Vulkan, Hailo-10H, SOPHGO, Tenstorrent, FPGA research and specialist vision.
- Benchmark contract validation in CI and new benchmark harness documentation.

### Changed

- Benchmark schema upgraded to v2 and now preserves raw samples, statistics, power scope, cost basis and workload class.
- Benchmark/release agent skills now enforce complete-node power and workload-comparability rules.
- v0.4 roadmap milestone is now the implementation baseline; real hardware result collection remains the next measurement phase.

## [0.3.0] - 2026-08-10

### Added

- First-class NPU, TPU, AI ASIC, FPGA/adaptive-SoC and decommissioned-accelerator catalog categories.
- Hailo-10H / Raspberry Pi AI HAT+ 2, SOPHGO BM1688 and BM1684X, Tenstorrent Wormhole n150s, AMD Kria KV260, AMD Versal AI Edge Gen 2, AMD Alveo V70, Google Coral Edge TPU, MemryX MX3 and Intel NCS2 reference entries.
- `docs/ACCELERATORS.md` with workload-routing, TOPS guardrails and accelerator benchmark requirements.
- Reusable `accelerator-research` agent skill.
- Accelerator metadata for family, host mode, software stack, LLM support, lifecycle, precision formats, power scope and workload role.
- Catalog schema v3 support for unresolved/EOL pricing without fake zero-dollar values.

## [0.2.0] - 2026-08-10

### Added

- Heterogeneous hardware catalog covering mini PCs, dev boards, embedded boards, SBCs and specialty/decommissioned hardware.
- Initial low-power cluster scoring, BOM and catalog CLI.
- Project governance, agent skills, catalog schemas and deterministic generated parts table.

## [0.1.0] - 2026-08-10

### Added

- Initial LowPowerLLMCluster project structure and catalog concept.
