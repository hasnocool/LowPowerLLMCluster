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
