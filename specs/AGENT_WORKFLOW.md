# Agent Workflow Specification

Before changing the project, an agent must:

1. read `AGENTS.md`, `docs/PROJECT_CHARTER.md`, and `docs/GUARDRAILS.md`;
2. identify whether the task changes catalog data, sourcing, evidence/estimation semantics, optional benchmarks, runtime code or release state;
3. use the matching skill under `.agents/skills/`;
4. preserve source attribution, memory semantics and confidence labels;
5. run the validation suite;
6. update docs and CHANGELOG for user-visible behavior/schema changes.

## Default task priority

When work could reasonably be either product/catalog work or benchmark-lab work, prefer the catalog task. Product discovery, exact configuration, current pricing, compatibility and evidence quality are the project's primary deliverables.

## Claims

Before calling one product better than another, say what dimension is being compared: price, included RAM, verified memory potential, software maturity, sourced measured throughput, measured energy efficiency, or another explicit factor. Do not turn a catalog score into a performance claim.

## Accelerator changes

Read `.agents/skills/accelerator-research/SKILL.md` and `docs/ACCELERATORS.md`. Runtime evidence is required before marking an accelerator as a plausible LLM candidate, but a full benchmark is not required to catalog/watch it.

## Benchmark changes

Benchmark work is optional supporting evidence. When modifying it, read `.agents/skills/benchmark-hardware/SKILL.md`, `docs/BENCHMARK_HARNESS.md`, and `specs/BENCHMARKING.md`, preserve non-blocking behavior, validate profiles, and keep workload/power boundaries explicit.
