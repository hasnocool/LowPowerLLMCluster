# Agent Workflow Specification

Before changing the project, an agent must:

1. read `AGENTS.md`, `docs/PROJECT_CHARTER.md`, and `docs/GUARDRAILS.md`;
2. identify whether the task changes catalog data, architecture, benchmarks, runtime code or release state;
3. use the matching skill under `.agents/skills/`;
4. preserve source attribution and confidence labels;
5. run the validation suite;
6. update docs and CHANGELOG for user-visible behavior/schema changes.

Before declaring a hardware candidate better than another, the agent must state whether the conclusion comes from manufacturer specifications, listing data, community measurements or project measurements.

## Accelerator changes

When a task adds or changes NPU/TPU/AI-ASIC/FPGA/adaptive/EOL accelerator data, agents must also read `.agents/skills/accelerator-research/SKILL.md` and `docs/ACCELERATORS.md`. Accelerator entries require runtime evidence and explicit power scope; TOPS alone is insufficient.

## Benchmark changes

When a task changes benchmark orchestration, metrics, power collection or result interpretation, agents must also read `.agents/skills/benchmark-hardware/SKILL.md`, `docs/BENCHMARK_HARNESS.md`, and `specs/BENCHMARKING.md`. Run `python scripts/validate_benchmark_profiles.py` and the test suite. New runtime adapters must preserve non-blocking subprocess/telemetry behavior and the workload/power-boundary rules.
