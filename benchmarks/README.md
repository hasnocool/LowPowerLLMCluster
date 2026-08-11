# Benchmark profiles

Profiles describe **how to measure one hardware configuration**. They are deliberately separate from results.

The example files are templates. Paths, runtime versions, commands, system cost and power probes must be changed to match the machine under test.

## Native llama.cpp path

`llama_cpp` invokes `llama-bench` directly and consumes its JSON output. It executes prompt processing and text generation as separate phases so the power sampler can keep prefill and decode windows separate.

## Vendor bridge contract

Hailo, SOPHGO, Tenstorrent and FPGA-native runtimes differ too much to pretend they share one CLI. Their adapters therefore invoke a runtime-specific command **without a shell** and require that command to emit the normalized JSON contract in `specs/adapter-output.schema.json`.

Minimal LLM example:

```json
{
  "fit_status": "runtime_verified",
  "metadata": {"runtime_version": "abc123", "backend": "BM1688"},
  "metrics": {
    "prompt_tokens_per_second": {"unit": "tokens/s", "samples": [120.1, 121.0, 119.8]},
    "generation_tokens_per_second": {"unit": "tokens/s", "samples": [18.4, 18.6, 18.5]}
  }
}
```

Specialist devices use their real workload metric instead:

```json
{
  "fit_status": "runtime_verified",
  "metrics": {
    "frames_per_second": {"unit": "frames/s", "samples": [92.0, 93.1, 92.7]}
  }
}
```

Do not convert FPS, audio realtime factor, embeddings/s and tokens/s into one magic score.
