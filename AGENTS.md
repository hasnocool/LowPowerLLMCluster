# Agent Instructions

## Mandatory reading order

1. `docs/PROJECT_CHARTER.md`
2. `docs/GUARDRAILS.md`
3. relevant spec under `specs/`
4. matching skill under `.agents/skills/`

## Project purpose

LowPowerLLMCluster is primarily a **catalog, sourcing and buying/research planner** for efficient and unusual local-AI hardware. Benchmarking is optional evidence tooling, not the main project.

## Rules that may not be traded away

- Preserve plain-language explanations and useful ASCII diagrams.
- Grow the catalog even when hardware cannot be locally tested.
- Keep manufacturer, seller, community, benchmark and derived-estimate claims distinct.
- Unknown performance is better than fabricated precision.
- Never derive tokens/sec directly from TOPS/TFLOPS/bandwidth/core count/TDP.
- `memory_capacity_gb` means included/fixed memory; barebones do not inherit CPU maximum RAM.
- Capacity/model-fit estimates must expose assumptions and warn that they are not throughput predictions.
- Machine-readable catalog fragments are authoritative; generated docs follow them.
- Discovery/history data is staging evidence until reviewed into canonical catalog fragments.
- Async source/history code must keep blocking network/filesystem/database operations off the event loop and avoid sharing non-thread-safe connections across workers.
- Preserve source URLs, source type and verification dates.
- Experimental/EOL hardware retains risk and lifecycle labels.
- Multi-source performance ranges require independent compatible measured sources; specialist metrics remain separate from LLM throughput.
- Benchmark code remains available but must not become a prerequisite for catalog inclusion/ranking.
- Update README, PARTS, CHANGELOG, TODO and relevant docs/specs with behavior changes.
- Use semantic versioning and Python 3.12+.

## Release/document invariants

- `VERSION`, `pyproject.toml`, package `__version__`, and latest CHANGELOG version agree.
- `python scripts/check_governance.py` passes.
- `python scripts/validate_catalog.py` passes.
- `python scripts/validate_evidence_records.py` passes.
- `python scripts/validate_benchmark_profiles.py` passes (optional benchmark subsystem remains healthy).
- `python scripts/render_parts_table.py` leaves `PARTS.md` clean.
- `pytest -q` passes.
