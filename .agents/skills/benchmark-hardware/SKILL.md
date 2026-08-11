# Hardware Benchmark Skill

Use when adding inference, power, fit or specialist-offload measurements.

1. Read `specs/BENCHMARKING.md` and `docs/BENCHMARK_HARNESS.md` before running or importing results.
2. Prefer `llm-cluster-bench` and the machine-readable profile/result contracts over ad-hoc shell scripts.
3. Capture raw native output before writing conclusions.
4. Record hardware ID, configuration ID, complete software/runtime identity, model hash/quantization and workload dimensions.
5. Keep prefill and decode separate for LLM workloads.
6. Use at least three measured runs; prefer five. Preserve samples plus median/spread.
7. Use non-blocking subprocess/telemetry collection in asynchronous orchestration. Never introduce synchronous polling loops into the async benchmark path.
8. Record the power boundary. Only `complete_node_input` may generate canonical tokens/joule or specialist units/joule.
9. Do not substitute TDP/TBP, CPU package telemetry or accelerator-board telemetry for complete-node input power.
10. Host-attached accelerators need complete-system acquisition cost before throughput/$ is considered canonical.
11. Specialist vision/audio/embedding devices keep workload-specific metrics. Do not blend FPS, embeddings/s or audio throughput into an LLM score.
12. Do not compare different model hashes, quantization, contexts or workload dimensions without clearly separating the result groups.
13. Store result JSON under `results/` when it is small/reproducible; link large raw traces instead of bloating git.
14. Update CHANGELOG/TODO/docs when benchmark capabilities or measurement semantics change.

## Graduation rule

A hardware candidate may be called benchmark-validated only when the project has a reproducible result containing runtime fit, throughput samples, sufficient provenance and the appropriate measurement boundary for any efficiency claim.
