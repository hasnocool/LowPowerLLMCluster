# v0.4 Measured Performance Harness

The benchmark harness exists to answer a practical question:

> **Which machine does the useful work we need for the fewest watts and dollars?**

It deliberately does **not** turn TOPS, TFLOPS, TDP, memory bandwidth or core counts into synthetic LLM performance.

## One result format, different native runtimes

```text
                         BENCHMARK PROFILE
                                │
               ┌────────────────┼─────────────────┐
               │                │                 │
               ▼                ▼                 ▼
          llama.cpp         vendor LLM       specialist AI
       CPU/Vulkan/CUDA    Hailo/SOPHGO/TT    vision/audio/etc.
               │                │                 │
               │          normalized JSON         │
               └────────────────┼─────────────────┘
                                ▼
                     MEASURED RESULT SCHEMA v2
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
          model fit          throughput       power + cost
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ▼
                     comparable efficiency
```

`llama.cpp` has a stable benchmark tool, so the harness parses `llama-bench -o json` directly. Hailo, SOPHGO, Tenstorrent and FPGA-native stacks keep their own native tools and use a small JSON bridge contract instead of pretending they share one CLI.

## LLM measurements

For LLM workloads the canonical metrics are:

- prompt/prefill tokens per second;
- generation/decode tokens per second;
- complete-node input watts by phase when available;
- prompt tokens/joule;
- generation tokens/joule;
- prompt throughput per purchase dollar;
- generation throughput per purchase dollar;
- model-fit status and basis.

`tokens/$` in this project means **throughput per acquisition dollar**, not a claim about electricity cost, lifetime value or API-equivalent pricing.

## Why prefill and decode stay separate

They stress hardware differently.

```text
prompt arrives
     │
     ▼
 PREFILL / PP
 lots of prompt tokens processed together
     │
     ▼
 DECODE / TG
 one autoregressive token after another
```

A GPU, CPU, NPU or TPU can be excellent at one phase and mediocre at the other. v0.4 therefore preserves both instead of averaging them into a single speed number.

For the native llama.cpp adapter, the harness invokes the prompt-processing and generation tests separately. This also gives the power sampler separate `prefill` and `decode` windows.

## Power truth boundary

The most important power rule is:

```text
CPU package watts      != wall/DC input watts
accelerator board watts != complete node watts
TDP/TBP                != measured watts
```

Only a power measurement with scope `complete_node_input` can generate the canonical tokens/joule or specialist units/joule values.

Other scopes are still useful telemetry and should be recorded, but the harness deliberately withholds canonical energy-efficiency metrics from them.

### Power providers

v0.4 supports:

- `command`: asynchronously invoke an external meter CLI and parse a watt value;
- `static_measured`: enter values actually measured with a meter when live integration is unavailable;
- `none`: benchmark throughput without inventing power numbers.

`static_measured` is **not** a place for TDP or manufacturer power specifications.

## Model fit

There are two fit concepts:

1. **preflight screening** — compare artifact file size with catalog memory using explicit headroom;
2. **runtime verification** — the actual runtime loaded/executed the model.

File-size screening is intentionally labeled heuristic because KV cache, runtime buffers, compiled artifacts and accelerator-specific layouts can materially change memory use.

## Specialist accelerators

A Coral, MemryX device or audio accelerator should not be made to look bad just because it cannot emit text tokens.

```text
LLM node                  specialist node
--------                  ---------------
tokens/s                  frames/s
prompt tokens/J           detections/J
generation tokens/J       embeddings/J
tokens/s/$                audio-seconds/s/W
```

The harness stores the device's **real primary metric** and calculates units/joule only within that workload class. The comparison command groups incompatible workload/model signatures separately.

## Vendor runtime bridge

Vendor adapters run an argv list directly with `asyncio.create_subprocess_exec`; they do not invoke a shell. Placeholders such as `{model_path}`, `{prompt_tokens}`, `{generated_tokens}` and `{runs}` are substituted into individual arguments.

The bridge command prints one JSON object matching `specs/adapter-output.schema.json`:

```json
{
  "fit_status": "runtime_verified",
  "metadata": {
    "runtime_version": "git-commit-or-sdk-version",
    "backend": "BM1688"
  },
  "metrics": {
    "prompt_tokens_per_second": {
      "unit": "tokens/s",
      "samples": [120.1, 121.0, 119.8]
    },
    "generation_tokens_per_second": {
      "unit": "tokens/s",
      "samples": [18.4, 18.6, 18.5]
    }
  }
}
```

This lets each vendor integration evolve independently while the result database stays stable.

## Commands

After an editable install:

```bash
llm-cluster-bench backends
llm-cluster-bench validate benchmarks/profiles/llama-cpu.example.json
llm-cluster-bench run my-profile.json
llm-cluster-bench compare results/*.json
```

The example profiles are templates; they are not claims that a given model/runtime combination has already been benchmarked.

## Comparison rule

A benchmark result is directly comparable only when these materially match:

- workload class;
- model identity/hash;
- quantization;
- context size;
- prompt token count;
- generated token count;
- primary specialist metric where applicable.

The CLI creates separate groups when they do not match instead of ranking apples against oranges.

## v0.4 limitations

The harness provides the measurement framework; it does not manufacture hardware results. Several vendor bridges still need small runtime-specific wrapper scripts on the actual hardware, and model-loaded-idle measurement requires a persistent-runtime adapter rather than a short-lived benchmark process. Those are explicit follow-on tasks rather than values inferred from spec sheets.
