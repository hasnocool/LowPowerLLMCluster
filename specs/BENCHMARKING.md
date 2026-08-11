# Benchmarking Specification

The project must eventually replace screening heuristics with reproducible measurements.

## Minimum benchmark matrix

For each usable backend/platform:

- llama.cpp version or commit
- backend: CPU, Vulkan, CUDA, ROCm/HIP, Metal, OpenCL or platform-specific runtime
- one small model that fits nearly every node
- one medium model appropriate to 16-32GB nodes
- one largest practical model for the platform
- fixed prompt and output token counts
- at least two context sizes
- prompt processing tokens/s
- generation tokens/s
- model-load time
- peak and steady memory use

## Power measurement

Record complete-node wall/DC-input watts whenever possible:

1. booted idle
2. model loaded idle
3. prompt/prefill
4. steady decode
5. peak observed

Compute energy efficiency from measured work and measured energy. Do not derive tokens/joule from TDP.

## Repetition

Use a warm-up run and at least three measured runs. Keep raw JSON results and report median plus spread. Thermal throttling is a result, not something to hide.

## Experimental modifications

Stock and modified configurations must be separate benchmark identities. BC-250 stock CU configuration and any community-unlocked configuration, for example, are different test targets.

## Accelerator-specific fields

When the device is host-attached or uses a non-llama.cpp runtime, also record:

- accelerator board/module ID and revision;
- host CPU/RAM and PCIe/USB/M.2 attachment details;
- driver, firmware, compiler and runtime versions;
- model conversion/compile command and output artifact hash;
- precision actually executed;
- accelerator-only power if available, with scope;
- complete-node input power;
- data-transfer overhead;
- whether throughput is prefill, decode, vision FPS, embedding throughput or another workload-specific metric.

Never compare specialist vision FPS to LLM tokens/sec through a single opaque score.
