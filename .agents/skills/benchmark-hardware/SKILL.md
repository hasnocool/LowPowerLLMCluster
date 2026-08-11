# Hardware Benchmark Skill

Use when adding inference or power measurements.

- Follow `specs/BENCHMARKING.md`.
- Capture raw machine-readable results before writing conclusions.
- Record complete software/hardware identity and model hash/quantization.
- Use non-blocking telemetry collection when benchmark orchestration is asynchronous.
- Do not compare results with different model, quantization, context or runtime settings without making the mismatch explicit.
- Prefer wall/DC-input power to package telemetry for tokens/joule.
