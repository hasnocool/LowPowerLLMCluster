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
- Exact-hardware stock 24-CU AMD BC-250 community llama.cpp/Vulkan prefill and decode evidence, explicitly separated from 40-CU unlock results.
- CAD buying reports for under CA$100, CA$250 and CA$500, 32GB+, low-power, weird-hardware, EOL and measured-evidence candidates.
- Broader official manufacturer/source seed registry, including Turing Pi, Radxa/ALLNET and Orange Pi references.
- Source-health history with last-success/failure state, result counts and consecutive-failure tracking.
- Exponential retry/backoff with jitter and numeric `Retry-After` handling for transient network, 429 and common 5xx failures.
- Stale-listing warnings based on last successful observation without deleting historical data or claiming the listing is gone.
- Named `daily-market` and `weekly-deep-scan` autonomous refresh profiles.
- Per-source `max_queries_per_run` and daily request-budget caps with persisted UTC-day usage state.
- Configurable watchlists for exact parts, categories, keywords, sources, memory and target-power constraints.
- Significant price-drop, stock-return, new-product, landed-cost-change and compatible benchmark regression/improvement alerts.
- Fingerprint-based alert deduplication so historical changes are not re-emitted every refresh.
- Compact `reports/current/daily-changes.md` and machine-readable `daily-changes.json` change-intelligence outputs.
- First-class `gpu_accelerator` catalog/sourcing category with fixed-VRAM and explicit board-power semantics.
- Initial discrete-GPU reference catalog covering RTX 5060 Ti 16GB, RTX 3090 24GB, RX 9070/9070 XT 16GB, Arc B580 12GB and Arc A770 16GB.
- GPU sourcing queries in both autonomous refresh profiles plus a dedicated `gpu-value` watchlist.
- Official NVIDIA/AMD/Intel GPU specification/reference URLs in the source registry without treating launch/reference pages as live street prices.
- Decision-quality engine using price-history position, conservative model-capacity fit, evidence confidence, opportunity freshness and price stability.
- Native-currency new-all-time-low detection so FX movement cannot fabricate a seller-price record.
- Price trend and volatility metrics for matched product histories.
- Source-class-aware opportunity freshness/expiry with seller end-time support when parseable.
- P1-P4 alert prioritization using alert type/severity, magnitude, current recommendation, confidence and opportunity urgency.
- Ranked `Buy`, `Watch`, `Ignore` and `Experimental` daily recommendations.
- Complete-node TCO engine covering product price, required host/RAM/storage/PSU/PCIe/cooling/chassis infrastructure, and multi-year electricity scenarios.
- Editable light/mixed/always-on/high-electricity TCO assumptions in `data/market/tco-scenarios.json`.
- TCO-aware recommendation re-ranking plus `reports/current/daily-tco.md` / `daily-tco.json`.
- Break-even analysis for product price, electricity rate and daily load hours between complete-node options.
- Ownership-aware TCO profiles: `new-build`, `reuse-host-core`, `reuse-complete-host`, and `reuse-everything`.
- Custom already-owned component overrides for TCO and break-even comparisons.
- Separate incremental infrastructure cost and avoided-acquisition value for compatible already-owned hardware.
- Live BOM product/cost sourcing for CPU/host, motherboard, RAM, storage, PSU, PCIe/OCuLink, cooling and chassis components.
- Cross-component complete-build solver for socket, memory, PCIe, PSU, form-factor, storage, GPU-clearance and cooler constraints.
- Exact-SKU manufacturer specification enrichment with identity verification before compatibility facts are admitted.
- Field-level manufacturer-spec provenance with source URL, observation time, extraction method, association ID and confidence.
- Exact/reference GPU board enrichment that can supply dimensions, slot width, PSU, connector, PCIe and Resizable BAR requirements without copying them to arbitrary partner cards.
- Initial exact/reference spec associations for MSI B550-A PRO, MSI PRO B660M-A DDR4, Corsair RM750e, Corsair 4000D Airflow, Intel Core i5-12400, RTX 3090 Founders Edition and Intel Arc B580 Limited Edition.
- Automatic manufacturer association discovery using normalized manufacturer + MPN identity, an official-domain registry, manufacturer-owned search pages when configured, bounded official sitemap discovery and conservative page identity scoring.
- Persistent verified/not-verified manufacturer association cache with expiry so exact-SKU coverage grows across refreshes without repeatedly rediscovering the same product page.
- Structured-source manufacturer/MPN preservation in Mouser, DigiKey and manufacturer JSON-LD listings.
- Conservative automatic manufacturer-page compatibility parsing for CPU, motherboard, PSU, chassis, cooler and exact GPU facts.
- Automatic manufacturer evidence retains association origin, cache-hit state, identity score and field-level extraction provenance.
- Structured manufacturer document ingestion for schema.org `Product.additionalProperty`, HTML specification tables, CPU/BIOS support matrices and same-manufacturer PDF manuals/datasheets before generic page-text parsing.
- Bounded manufacturer-PDF text extraction through `pypdf` without OCR, with PDF URLs and source class retained in field-level provenance.
- Structured evidence priority that lets exact curated fields win, then structured page/manual evidence fill unresolved fields, with flattened-page regexes used only as the final fallback.
- `docs/STRUCTURED_MANUFACTURER_INGESTION.md` plus deterministic fixtures covering JSON-LD properties, spec tables, BIOS support matrices, PDF-link filtering and provenance.
- `llm-cluster-refresh manufacturer-config` and `manufacturer-associations` inspection commands.
- Persisted `data/market/spec-evidence.json`, `data/market/manufacturer-associations.json` and `data/market/compatible-builds.json` evidence/build state.
- `llm-cluster-refresh spec-config`, `spec-evidence`, `refresh-bom`, and `compatible-builds` operator workflows.
- `docs/EXACT_SKU_ENRICHMENT.md` methodology and extension guide.
- `llm-cluster-refresh tco`, `recommendations --scenario`, ownership flags, `break-even`, and `tco-scenarios` commands.
- `reports/current/daily-recommendations.md` and machine-readable `daily-recommendations.json` outputs.
- `docs/GPUS.md`, `docs/DECISION_QUALITY.md`, and `docs/TOTAL_COST_OF_OWNERSHIP.md` guides.
- `llm-cluster-refresh` CLI for profile execution, health inspection, stale warnings, source budgets, watchlists, alerts, recommendations, TCO and report regeneration.
- Scheduled GitHub Actions refresh that can use optional marketplace secrets, refresh Bank of Canada FX, regenerate current reports/change intelligence/decision reports and commit changed evidence.
- `docs/AUTONOMOUS_REFRESH.md` and `docs/CHANGE_INTELLIGENCE.md` operational guides.
- `llm-cluster-market` CLI with `discover`, `history`, `landed`, `refresh-fx`, `ingest-performance`, `aggregate-performance`, and `report` workflows.
- `specs/MARKET_INTELLIGENCE.md` and tests for matching, history deduplication, seller confidence, lifecycle tracking, landed-cost math, evidence ingestion, compatible aggregation, JSON-LD normalization, CAD report behavior, retry policy, stale detection, source budgets and change-alert deduplication.
- Decision-quality and TCO tests covering GPU VRAM model-fit screening, all-time-low detection, trend/volatility, opportunity expiry, alert prioritization, host infrastructure, ownership reuse, board-power scope and complete-system comparisons.
- Exact-SKU enrichment tests covering association priority, field provenance, provisional-to-compatible promotion and manufacturer-evidence-driven rejection.
- Automatic manufacturer discovery/parser tests covering cache reuse, PSU connectors/power, motherboard lane-sharing facts, chassis clearances and exact GPU physical requirements.

### Changed

- Live market I/O uses `httpx.AsyncClient`; blocking filesystem work is isolated from the event loop.
- Failed, credential-disabled or budget-exhausted sources cannot generate false listing-disappearance events.
- v0.5 keeps the catalog authoritative while listings, prices, FX rates, seller reputation, source budgets and benchmark records remain time-stamped evidence layers.
- Benchmark evidence stays attached to the exact tested product/configuration instead of being copied across boards that merely share a SoC.
- CAD reports prefer active live listing observations and fall back to clearly labeled catalog midpoint pricing only when sourced FX is available.
- Community energy-efficiency evidence preserves its published measurement boundary; internal Jetson rail telemetry is not relabeled as complete-node wall-input power.
- Discrete GPU TGP/TBP is treated as host/PSU/cooling friction, never as complete-node tokens/joule.
- Daily recommendations are explainable buying decisions rather than synthetic hardware-performance rankings.
- Final recommendation ordering incorporates complete-node acquisition and scenario operating cost so component-only sticker prices cannot hide required infrastructure.
- Already-owned compatible infrastructure now has zero incremental acquisition cost while remaining part of complete-node operating-power calculations.
- Exact manufacturer specification facts override weaker title-derived compatibility facts only at the individual field level.
- Generic GPU family listings remain provisional for board-specific dimensions/connectors unless an exact/reference-board association or automatically verified board-partner MPN association exists.
- Automatic manufacturer discovery never broadens authority beyond the configured official manufacturer domains.
- Structured manufacturer evidence is consumed before generic flattened-page regexes; weaker sources can fill missing fields but do not overwrite stronger verified values.
- Complete-build ranking prefers fully compatible builds, then better manufacturer-spec coverage, before relying on provisional unknowns.

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
