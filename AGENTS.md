# Agent Instructions

## Mandatory reading order

1. `docs/PROJECT_CHARTER.md`
2. `docs/GUARDRAILS.md`
3. relevant spec under `specs/`
4. matching skill under `.agents/skills/`

## Project purpose

LowPowerLLMCluster is primarily a **catalog, sourcing and buying/research planner** for efficient and unusual local-AI hardware. Benchmarking is optional evidence tooling, not the main project.

Discrete GPUs are a first-class sourcing family alongside mini PCs, SBCs, mobile boards, NPUs, TPUs, AI ASICs, FPGAs and decommissioned accelerators.

## Rules that may not be traded away

- Preserve plain-language explanations and useful ASCII diagrams.
- Grow the catalog even when hardware cannot be locally tested.
- Keep manufacturer, seller, community, benchmark and derived-estimate claims distinct.
- Unknown performance is better than fabricated precision.
- Never derive tokens/sec directly from TOPS/TFLOPS/bandwidth/core count/TDP/TGP/TBP.
- `memory_capacity_gb` means included/fixed RAM or fixed VRAM; barebones do not inherit CPU maximum RAM.
- Discrete GPUs must keep fixed VRAM, exact board/listing evidence and board-power scope distinct from host/system power.
- Capacity/model-fit estimates must expose assumptions and warn that they are not throughput predictions.
- Machine-readable catalog fragments are authoritative; generated docs follow them.
- Preserve source URLs, source type and verification dates.
- Experimental/EOL hardware retains risk and lifecycle labels.
- Benchmark code remains available but must not become a prerequisite for catalog inclusion/ranking.
- Daily Buy/Watch/Ignore/Experimental recommendations must remain explainable from price history, capacity fit, confidence, risk and freshness.
- All-time-low detection must not manufacture seller-price records from FX movement.
- Opportunity expiry is a decision-freshness TTL unless a seller end time is explicit; do not claim an item will definitely disappear.
- GPU board TGP/TBP may inform host/PSU/cooling friction but is not complete-node energy efficiency.
- Update README, PARTS, CHANGELOG, TODO and relevant docs/specs with behavior changes.
- Use semantic versioning and Python 3.12+.

## Release/document invariants

- `VERSION`, `pyproject.toml`, package `__version__`, and latest CHANGELOG version agree.
- `python scripts/check_governance.py` passes.
- `python scripts/validate_catalog.py` passes.
- `python scripts/validate_benchmark_profiles.py` passes (optional benchmark subsystem remains healthy).
- `python scripts/render_parts_table.py` leaves `PARTS.md` clean.
- `pytest -q` passes.
