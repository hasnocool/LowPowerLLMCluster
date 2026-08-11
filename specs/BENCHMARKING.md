# Benchmarking Specification

> **Optional evidence subsystem:** the catalog does not require physical ownership or a local benchmark. Use this only when reproducible measurements are available.

This specification governs measured performance records. Screening heuristics remain useful for discovery but cannot graduate hardware into a recommendation.

## Result contracts

- input profile: `specs/benchmark-profile.schema.json`
- vendor bridge output: `specs/adapter-output.schema.json`
- normalized result: `specs/benchmark.schema.json` (schema v2)

Raw/native output must be retained in the normalized record or referenced as an artifact.

## Minimum LLM benchmark matrix

For each usable backend/platform record:

- hardware catalog ID and configuration ID;
- runtime version or git commit;
- backend: CPU, Vulkan, CUDA, ROCm/HIP, Metal, or platform-specific runtime;
- model name, artifact hash and quantization;
- fixed prompt and generated token counts;
- context size and context depth where applicable;
- at least three measured repetitions;
- prompt processing samples and median tokens/s;
- generation samples and median tokens/s;
- power measurement scope and source;
- complete-system acquisition cost when cost efficiency is calculated.

Use a small shared model, a medium model appropriate to the memory class, and the largest practical model for the platform as the test library grows.

## Native llama.cpp adapter

Use `llama-bench` JSON output. Prompt processing and generation are separate tests. Preserve llama.cpp build commit, build number, CPU/GPU identity, backend, thread count and GPU-layer placement when emitted by the tool.

The benchmark harness does not include tokenization/sampling latency in llama.cpp throughput because `llama-bench` itself measures inference kernels rather than full application latency. Do not relabel those numbers end-to-end request throughput.

## Vendor-native adapters

Hailo, SOPHGO, Tenstorrent and FPGA/adaptive runtimes may use their own benchmark/demo programs. A bridge must emit the normalized adapter JSON contract. The bridge is responsible for mapping the native runtime's measurements honestly.

Do not scrape human-formatted console output when a machine-readable API/output can be added to the bridge.

## Power measurement

Record complete-node wall/DC-input watts whenever possible:

1. booted idle;
2. model-loaded idle when a persistent runtime supports it;
3. prompt/prefill;
4. steady decode;
5. peak observed when available.

Power scopes must be explicit. Examples:

- `complete_node_input` — canonical efficiency scope;
- `accelerator_board` — useful auxiliary telemetry;
- `soc` — useful auxiliary telemetry;
- `cpu_package` — useful auxiliary telemetry.

Only `complete_node_input` may produce canonical tokens/joule or specialist units/joule. Never derive tokens/joule from TDP/TBP.

## Repetition and statistics

Use at least three measured runs. Prefer five. Store raw samples plus median, mean, population standard deviation, minimum and maximum. Thermal throttling and run-to-run variance are results, not noise to hide.

## Model fit

Record both:

- preflight fit estimate and its basis;
- runtime fit status.

A file-size-versus-RAM check is only a discovery heuristic. Runtime-verified model loading takes precedence.

## Cost efficiency

For complete systems calculate throughput per purchase USD using complete-system acquisition cost. Host-attached accelerators must include the host cost before canonical `throughput/$` is emitted.

This metric is acquisition efficiency only. Do not describe it as lifetime cost, electricity cost, or API-equivalent value.

## Specialist workloads

Vision, audio, embedding and other specialist workloads keep workload-specific metrics such as:

- frames/s;
- detections/s;
- embeddings/s;
- audio-seconds processed per second;
- latency where relevant.

Calculate units/joule only from complete-node input power. Never compare specialist FPS or audio throughput against LLM tokens/s through one opaque score.

## Experimental modifications

Stock and modified configurations are separate benchmark identities. BC-250 stock and any firmware/CU-unlocked configuration, FPGA bitstreams, power caps, overclocks and runtime patches must each receive a distinct `configuration_id`.

## Async orchestration

Benchmark subprocess execution and live telemetry collection must not block the event loop. Use asynchronous subprocess APIs and thread off unavoidable blocking file operations. Do not introduce `subprocess.run()` or synchronous polling loops into asynchronous benchmark orchestration.
