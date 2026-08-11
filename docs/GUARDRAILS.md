# Project Guardrails

These rules keep the project from drifting into a generic hardware catalog.

## 1. Evidence hierarchy

Use sources in this order when available: manufacturer documentation -> project/runtime documentation -> reproducible benchmark artifacts -> reputable technical reporting -> marketplace listing -> community report. Preserve the source type in notes.

## 2. Separate four kinds of claims

Every hardware record may contain:

- **manufacturer facts**: silicon, memory interface, supported power modes;
- **seller facts**: price, included RAM/SSD, ports, MOQ;
- **community observations**: compatibility, unofficial unlocks, driver workarounds;
- **project measurements**: our reproducible benchmarks and wall-power measurements.

Never silently promote one class into another.

## 3. No fake performance

A TOPS number, FLOPS estimate, core count or memory bandwidth number is not a llama.cpp benchmark. Synthetic screening scores must be labelled as such. Real ranking eventually comes from measured workloads.

## 4. Whole-system power matters

Prefer wall-input power for final energy comparisons. Package TDP is useful for discovery but cannot be substituted for node watts. Record idle, model-load, prompt/prefill and steady decode separately.

## 5. Heterogeneous by design

The cluster may contain x86, Arm, NVIDIA CUDA, AMD Vulkan, Rockchip and other nodes. The router should dispatch complete jobs to the best node whenever possible. Network model sharding is a fallback for capacity problems, not the default path.

## 6. Experimental hardware stays experimental

BC-250-style hardware is welcome, but unofficial firmware, CU unlocks, patched kernels and unusual power/cooling requirements must remain visibly labelled. A cheap experimental board must not outrank a stable node merely because a single community benchmark looks impressive.

## 7. Optimize for practical ownership

Track acquisition cost, RAM included, required PSU/cooling, storage, networking, software setup burden, reliability evidence and replacement availability. Cheap silicon can become expensive once the missing infrastructure is counted.

## 8. Documentation is part of the feature

Keep plain-language explanations and ASCII diagrams. When catalog schema, architecture or behavior changes, update README, PARTS, relevant specs, TODO and CHANGELOG in the same change.

## 9. Reproducibility

Benchmarks must record hardware revision, firmware/BIOS, OS/kernel, runtime commit/version, backend, model hash, quantization, context, batch settings, power mode and measurement boundary.

## 10. Automation guardrail

Price refreshers must be non-blocking when integrated into asynchronous services, rate-limited, source-attributed and able to fail without corrupting the last known-good catalog.
## 11. Accelerator capability is workload-specific

NPU, TPU, AI ASIC and FPGA labels do not imply general LLM compatibility. Record the compiler/runtime path and intended workload. Fixed-function vision hardware remains a specialist unless a reproducible transformer path exists.

## 12. Power boundaries must be explicit

Accelerator chip power, module power, board TDP and complete-node input power are different measurements. Store the boundary with every number and use complete-node measurements for final tokens/joule comparisons.

## 13. EOL hardware needs an exit-risk penalty

Discontinued hardware can be a bargain, but frozen drivers, unavailable toolchains, missing replacement parts and unsupported kernels are part of ownership cost. Keep lifecycle status visible and do not invent a price when the current used market has not been resolved.

## 14. Benchmark compatibility is a contract

Do not rank results together when model identity/hash, quantization, workload class, context or token counts materially differ. The benchmark CLI may group mismatched results separately, but an agent must not collapse those groups into one leaderboard.

## 15. Energy efficiency uses measured input energy

Canonical tokens/joule or specialist units/joule require `complete_node_input` power. Use the measured window's energy/duration average when available. Median watt samples are descriptive telemetry, not the preferred energy denominator.

## 16. Example profiles are not benchmark evidence

Files under `benchmarks/profiles/` are configuration templates. Placeholder paths, commands or settings must never be cited as hardware results. Only normalized records produced from actual runs belong in performance conclusions.
