# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-08-10

### Added

- Asynchronous product-discovery adapter contract plus deterministic JSON feed importer.
- Normalized listing model and concurrent multi-source discovery with source/listing deduplication.
- Append-only price observation history linked back to catalog part IDs.
- Exact-SKU/configuration confidence scoring that does not confuse CPU theoretical RAM limits with installed RAM.
- Evidence-backed CAD conversion input and explicit Canadian landed-cost breakdown for item, shipping, duty, brokerage and tax.
- Sourced vendor/community performance ingestion requiring model, runtime, workload, metric, unit and source URL provenance.
- `llm-cluster-market` CLI with `discover`, `history`, `landed`, and `ingest-performance` workflows.
- `specs/MARKET_INTELLIGENCE.md` and tests for matching, history deduplication, landed-cost math and evidence ingestion.

### Changed

- Market I/O boundaries are async-first; blocking file/SDK work is isolated from the event loop.
- v0.5 keeps the catalog authoritative while listings, prices and benchmark records remain time-stamped evidence layers.

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
