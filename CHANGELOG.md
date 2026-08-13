# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-08-12

### Added

- Bounded asynchronous catalog discovery pipeline with generic JSON-feed and schema.org JSON-LD product-page adapters.
- Non-blocking SQLite catalog history with price, currency, title, stock, disappearance and reappearance change events.
- Discovery normalization for form factor, dimensions, DC input, PSU/cooling/host requirements, board-RAM evidence and exact-SKU metadata.
- Seller, source and exact-SKU confidence scoring.
- Explicit-FX CAD conversion and Canada landed-cost estimates with shipping, duty, brokerage and province-tax planning assumptions.
- Catalog reports for sub-$100/$200/$500 candidates, high-memory bargains, low-power nodes, weird hardware and EOL bargains.
- Self-contained interactive HTML catalog dashboard with comparison selection and saved browser filters.
- Sourced performance-record model and JSON/JSONL importer carrying hardware/model/runtime/workload/quantization/context/power provenance.
- Confidence-aware measured performance ranges that require multiple independent compatible sources.
- Model-fit presets for common 1B-70B quantized model classes while preserving the capacity-only warning.
- Explicit published-power boundary helper that distinguishes accelerator/board measurements from processor TDP/cTDP.
- Discovery configuration and performance-record schemas, example discovery configuration, initial watchlist, and one vendor-provenance Hailo-10H record.
- Tests for asynchronous discovery, JSON-LD extraction, history/change detection, normalization/confidence, landed-cost estimates, performance ranges, power scope, reports and model presets.

### Changed

- Catalog shortlist scoring now incorporates seller/source and exact-SKU confidence when those fields exist without converting marketing compute specifications into performance.
- Board maximum-memory evidence can now carry a source URL/verification date and receives stronger confidence than an unlinked maximum.
- CLI now supports `discover`, `report`, `dashboard`, `landed-cost` and `performance-range`, plus `fit --preset` and `list --min-sku-confidence`.
- `TODO.md`, sourcing/evidence/catalog specifications and catalog-curation agent guidance now describe the automated refresh workflow and the next promotion/evidence work.
- Benchmarking remains optional and specialist metrics remain isolated from LLM throughput.

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
- Modular catalog manifest plus category-sized JSON fragments to reduce merge conflicts as the hardware universe grows.

### Changed

- Screening and BOM code now handles unresolved prices safely.
- LLM screening explicitly excludes TOPS/TFLOPS from the heuristic.
- Fixed-function vision accelerators are cataloged as specialists rather than mislabeled LLM workers.
- Project charter and guardrails now cover accelerator power boundaries, runtime evidence and lifecycle risk.

## [0.2.0] - 2026-08-10

### Added

- Expanded project scope from Ryzen laptop-class nodes to heterogeneous mini PCs, development boards, SBCs, embedded boards and specialty compute.
- AMD BC-250 experimental candidate with explicit community-evidence and risk labels.
- NVIDIA Jetson Orin Nano Super, Orange Pi 5 Plus 32GB, Radxa ROCK 5 ITX+ 32GB, MINISFORUM BD795M, Framework Ryzen AI mainboard and Intel N100 control-plane references.
- Project charter and mechanical guardrails.
- Hardware catalog, benchmark, scoring and agent-workflow specifications.
- Five reusable agent skills for hardware research, catalog curation, benchmarking, architecture review and release governance.
- PR and hardware-candidate templates.
- Mechanical version/document governance check in CI.

### Changed

- Screening score now supports heterogeneous hardware and explicitly avoids CPU-core-based cross-architecture performance claims.
- Parts table now supports Alibaba, AliExpress and manufacturer/reference sources instead of labelling every URL as Alibaba.

## [0.1.0] - 2026-08-10

### Added

- Initial low-power distributed LLM cluster architecture.
- Alibaba hardware-market snapshot with prices, URLs, seller verification state and plain-language rationale.
- Ryzen 7 7735U, Ryzen 7 8845HS, Ryzen 7 8745HS and Ryzen AI 9 HX 370 node candidates.
- 2.5GbE switch, DDR5 SO-DIMM and NVMe sourcing leads.
- ASCII architecture, power, networking and model-placement diagrams.
- Machine-readable `data/parts.json` catalog.
- CLI node-ranking and BOM calculations.
- Catalog validation, stale-price checks and generated PARTS.md workflow.
- GitHub Actions validation workflow.
