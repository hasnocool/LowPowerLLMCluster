# Scoring Specification

## Two scoring systems with different jobs

LowPowerLLMCluster keeps **catalog scoring** and **measured workload scoring** separate.

`llm-cluster rank` remains a shopping/research shortlist. It may use current acquisition price, included/fixed memory or discounted configurable memory potential, published power hints, software maturity, lifecycle/availability, and setup/ownership risk. It must not use TOPS, TFLOPS or invented tokens/sec.

`llm-cluster-optimize` is an evidence-backed workload placement tool. It may use measured or explicitly sourced throughput, complete-node power, memory capacity/bandwidth, cost and operational evidence. Missing performance remains missing; theoretical compute never becomes synthetic tokens/sec.

## Normalized 0-100 dimensions

The optimizer exposes independent dimensions instead of hiding all tradeoffs inside one number:

- `llm_speed` — measured/sourced decode, prefill and latency;
- `model_capacity` — usable AI memory, verified Q4 model capacity, bandwidth and context capacity;
- `ai_compute` — theoretical cross-precision FP/INT capability, confidence-adjusted and only across supported metrics;
- `power_efficiency` — measured tokens/joule, complete-system watts, idle power and sustained ratio;
- `cost_efficiency` — measured throughput/$, usable memory/$, bandwidth/$ and energy efficiency;
- `off_grid` — tokens/joule, absolute load/idle power, DC powerability, sleep/wake, cooling and reliability.

The default optional composite is:

```text
25% LLM speed
20% model capacity
10% AI compute
15% power efficiency
15% cost efficiency
15% off-grid
```

The off-grid profile shifts weight toward efficiency and absolute power:

```text
20% LLM speed
20% model capacity
 5% AI compute
25% power efficiency
10% cost efficiency
20% off-grid
```

Missing dimensions are not treated as zero. Available weights are renormalized and coverage is reported.

## Percentile normalization

Raw metrics are normalized against the current comparison population with duplicate-safe midpoint percentiles. This avoids fixed ceilings that become obsolete when hardware improves.

For metrics such as throughput, capacity and bandwidth, higher is better. For latency, watts, energy/task and price, lower is better and the percentile is inverted.

Every normalized metric is multiplied by its evidence confidence. Supported provenance includes measured local, community measured, vendor measured, manufacturer/theoretical, derived estimate, spec-based estimate and unknown.

## Hard compatibility gates

Known incompatibility is different from poor performance. Before ranking, the optimizer can reject candidates for:

- insufficient verified usable AI memory for the requested model;
- insufficient verified context capacity;
- measured decode/prefill below a requested minimum;
- complete-system power above a power budget;
- acquisition price above budget;
- missing required runtime or precision support;
- unsupported workload class;
- task energy above an explicit Wh budget.

Unknown data does not become an invented failure or invented success; it lowers coverage and is visible in the result.

## Safe model-capacity planning

The capacity gate uses the same transparent planning idea as `llm-cluster fit`:

```text
weights_gb = parameters_b × bits_per_weight / 8
planning_gb = weights_gb × 1.12 + 2GB
```

This is a conservative screening estimate, not a promise that a specific model/backend/context will fit.

## Derived energy metrics

When measured/sourced decode throughput and **complete-node input power** are both available, arithmetic-only derivatives may be calculated:

```text
tokens/joule = decode_tokens_s / system_watts
joules/token = system_watts / decode_tokens_s
tokens/kWh   = 3,600,000 / joules_per_token
```

With an explicit task size, the optimizer also derives task seconds, joules/task, Wh/task, battery runtime/tokens and solar-recovery hours. These are arithmetic transformations of supplied evidence; they never infer throughput from TOPS/TFLOPS.

Board-only accelerator power must not produce canonical whole-system tokens/joule. The benchmark-result bridge only accepts `complete_node_input` power for that purpose.

## Workload profiles

Built-in profiles are:

- `interactive_chat`;
- `coding_agent`;
- `long_context`;
- `always_on_agent`;
- `off_grid_ai`;
- `vision`.

Profiles weight different evidence and may define a minimum usability floor. A device that is exceptionally efficient but unusably slow therefore cannot win solely by consuming little power.

## Operational dimensions

Operational evidence stays visible alongside performance:

- software support: runtimes, quantization, OS, drivers, multi-device and deployment support;
- deployability: installation, drivers/firmware, power/cooling, host compatibility, runtime setup and model conversion;
- reliability: reproducible soak duration, crashes, resets, inference errors, throughput variance, thermal throttling, recovery/watchdog/ECC;
- sustained ratio: long-run throughput divided by burst throughput;
- thermal headroom: throttle temperature minus sustained temperature;
- energy proportionality: how much power falls from loaded to idle.

The optimizer reports theoretical and practical scores separately so high paper TOPS cannot conceal weak runtime support or measured performance.

## Pareto selection

When task time and task Wh are available, `--pareto` removes candidates dominated by another device that is both faster and lower-energy. This is often more robust than forcing every decision into one weighted average.

## Cluster measurements

Multiple nodes can be summarized with aggregate usable memory, combined idle/load watts and ideal independent decode throughput. When a real combined distributed benchmark is supplied:

```text
scaling_efficiency = measured_combined_decode / sum(independent_decode)
```

The system does not assume perfect multi-node scaling.

## Catalog score remains separate

Memory confidence rules still apply to the shopping score:

1. included/fixed RAM — strongest;
2. verified board maximum — useful but requires additional purchase;
3. CPU theoretical maximum — weak and heavily discounted;
4. unknown — little/no capacity credit.

A high catalog score means **worth investigating**. A high optimizer score means **strong for this evidence-backed workload and constraint set**. Neither is a substitute for provenance.