# Scoring Specification

## Two-stage ranking

### Stage A — discovery/screening

Before hardware is benchmarked, `llm-cluster rank` uses a deliberately conservative heuristic based on:

- usable memory capacity
- target power
- price
- trustworthy memory bandwidth when available
- software maturity
- hardware risk
- useful cluster I/O

It is a shortlist score only.

### Stage B — measured ranking

Once measurements exist, the preferred score must be workload-specific and based on real data such as:

- generation tokens/joule
- prompt tokens/joule
- generation tokens per purchase dollar
- maximum useful model/context capacity
- idle energy cost
- software/reliability penalty
- complete node cost including required RAM, storage, cooling and PSU

Never combine fundamentally different workloads into one unexplained number. Show the component metrics next to any composite score.

## Accelerator rule

Peak TOPS/TFLOPS are **not** inputs to Stage A scoring. Precision formats, compiler coverage, memory architecture and workload shapes differ too much for a raw compute number to be comparable. Accelerators can receive screening scores only when `llm_candidate=true`, pricing is resolved, usable model memory is known and a real LLM/VLM runtime path exists.

Fixed-function specialist accelerators should be evaluated with workload-specific metrics such as frames/joule or whole-cluster energy saved, not forced into a tokens/joule ranking.
