# Model Placement

Model size is affected by architecture, quantization and context/KV cache, so RAM capacity should be treated as a budget rather than a simple parameter-count conversion.

A practical first-pass node taxonomy is:

```text
32GB NODE
├── tiny utility models
├── 3B / 7B / 8B
├── many 12B / 14B quantizations
└── room becomes tight as context grows

64GB NODE
├── everything above
├── many 20B-32B quantized models
├── larger context budgets
└── several small services at once

96GB+ NODE
├── heavier 32B workloads
├── some aggressively quantized 70B-class experiments
├── larger MoE/model combinations
└── more room for KV cache and concurrent sessions
```

Do not interpret this diagram as a guarantee that every model in a parameter class will fit. The project should eventually calculate memory from the actual GGUF metadata and requested context size.
