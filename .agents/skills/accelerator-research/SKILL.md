# Accelerator Research Skill

Use when researching NPUs, TPUs, AI ASICs, FPGAs, adaptive SoCs, host-attached AI modules, or decommissioned accelerators.

1. Read `docs/PROJECT_CHARTER.md`, `docs/GUARDRAILS.md`, `docs/ACCELERATORS.md`, and `specs/HARDWARE_CATALOG.md`.
2. Identify the **actual workload path** before collecting marketing compute numbers: LLM/VLM generation, embeddings, vision, audio, or custom research.
3. Find first-party evidence for memory, supported precisions, host interface, power scope, lifecycle and software stack.
4. Find current model/runtime evidence. A TOPS number without a compiler/runtime path is not enough to mark `llm_candidate=true`.
5. Record host requirements. M.2/PCIe/USB accelerators are not complete nodes and must include the host in eventual cost/power measurements.
6. Mark fixed-function vision accelerators as specialists rather than LLM candidates unless a reproducible general transformer path exists.
7. For FPGA/adaptive hardware, distinguish stock DPU capability from a proposed custom datapath. Do not call theoretical custom logic a benchmark.
8. For EOL hardware, record `lifecycle_status`, unresolved pricing honestly, software-support risk, and the used-price threshold that would justify testing when possible.
9. Keep accelerator-chip, accelerator-board, SOM, and complete-node power scopes separate.
10. Update the appropriate `data/catalog/*.json` fragment (and the manifest only when structure changes), regenerate `PARTS.md`, update `docs/SOURCES.md`, and run catalog/governance/tests.

## Graduation rule

An accelerator can move from research/watch status to a recommended LLM worker only after the project has reproducible evidence for:

- model compilation/loading;
- model capacity;
- prompt and decode throughput;
- complete-node power;
- stable repeated runs;
- acquisition cost;
- software-maintenance burden.
