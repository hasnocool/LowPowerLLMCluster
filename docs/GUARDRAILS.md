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
