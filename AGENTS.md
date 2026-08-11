# Agent Instructions

## Mandatory reading order

Before making changes, read:

1. `docs/PROJECT_CHARTER.md`
2. `docs/GUARDRAILS.md`
3. the relevant specification under `specs/`
4. the matching agent skill under `.agents/skills/`

## Project purpose

Build a low-cost, low-power distributed local-LLM inference platform by discovering and **measuring** the best commodity and unusual hardware: mobile-CPU boards, mini PCs, SBCs, dev boards, embedded systems, edge-AI kits, NPUs, TPUs, AI ASICs, FPGAs, adaptive SoCs and decommissioned/specialty hardware such as AMD BC-250 and Alveo-class accelerators.

## Rules that may not be traded away

- Preserve plain-language explanations and useful ASCII diagrams.
- Keep manufacturer, seller, community and project-measured claims distinct.
- Never turn a listing price, TOPS value or theoretical hardware figure into a benchmark claim.
- Prefer measured tokens/joule and tokens/dollar over marketing metrics.
- Keep machine-readable data as the source of truth and generate tables from it.
- Preserve source URLs, source type and verification dates for market data.
- Prefer whole requests on one suitable node; treat network model sharding as an optional capacity fallback.
- Experimental hardware must keep explicit risk/software-maturity labels.
- Accelerator entries must distinguish LLM-capable, specialist-only, research-only and unproven runtime paths; TOPS alone never grants `llm_candidate=true`.
- Host-attached accelerators must eventually be measured with host cost and complete-node power, not accelerator-only power.
- Any async service code must use non-blocking I/O and thread-safe operations; move blocking work off the event loop.
- Update README, PARTS.md, CHANGELOG.md, TODO.md and relevant docs/specs when their truth changes.
- Use semantic versioning.
- Keep Python compatible with Python 3.12+.

## Release/document invariants

- `VERSION`, `pyproject.toml`, package `__version__`, and latest CHANGELOG version must agree.
- `python scripts/check_governance.py` must pass.
- `python scripts/validate_catalog.py` must pass.
- `python scripts/render_parts_table.py` must leave `PARTS.md` clean in git.
- `pytest -q` must pass.
