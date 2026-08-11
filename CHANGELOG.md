# Changelog

All notable changes to this project will be documented here.

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
