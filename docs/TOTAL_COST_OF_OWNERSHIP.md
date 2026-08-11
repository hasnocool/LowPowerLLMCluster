# Complete-Node Total Cost of Ownership

The project compares **usable systems**, not isolated sticker prices.

A CA$500 GPU is not a CA$500 inference node when it still needs a CPU/host, motherboard, RAM, storage, PSU, PCIe/OCuLink hardware, cooling and chassis. Likewise, a barebone mini PC may need RAM/storage before it is comparable with a complete system.

## Full discrete-GPU build stack

```text
GPU / accelerator
      │
      ├── CPU / host processor
      ├── motherboard
      ├── RAM
      ├── storage
      ├── PSU
      ├── PCIe / OCuLink / riser / adapter
      ├── cooling
      ├── chassis
      └── misc integration
      │
      ▼
complete-node acquisition cost
      │
      +
 idle/load energy scenario
      │
      ▼
 total cost of ownership
```

`data/market/tco-scenarios.json` contains **planning assumptions**, not live quotations. The CPU/host, motherboard, RAM, storage, PSU, chassis, cooling and integration lines are intentionally separate so they can later be replaced independently with sourced local prices.

## Deployment profiles

The TCO engine infers a conservative deployment profile from catalog metadata:

- `complete_system` — product is treated as usable without a separate host stack;
- `barebone_or_board` — adds RAM, storage, power, cooling and chassis assumptions;
- `host_attached_pcie` — adds CPU/host, motherboard, host RAM, storage, PSU, PCIe adapter, cooling, chassis and misc integration;
- `host_attached_usb` — adds CPU/host, motherboard, RAM, storage, power and chassis;
- `module_requires_carrier` — adds a carrier board and supporting infrastructure;
- `standalone_board` — adds storage/power/cooling/chassis planning costs.

These profiles should become more exact as catalog records gain explicit included-component evidence.

## Power evidence boundaries

A GPU's TBP/TGP is **not** complete-node wall power. When only board power exists, the planning model creates a low-confidence complete-node estimate by adding explicit host idle/load assumptions plus PSU/cooling overhead. The result is labeled:

`estimated_complete_node_from_board_power_plus_host_assumptions`

It must never be presented as measured tokens/joule or measured wall input. A real `complete_node_input` measurement remains the preferred evidence for final efficiency comparisons.

## Operating scenarios

The shipped scenarios cover occasional, mixed, always-on and higher-electricity sensitivity cases. Each scenario records load hours/day, idle hours/day, days/year, CAD/kWh assumption and ownership years. These are editable planning assumptions, not claims about a user's tariff.

## Break-even analysis

The TCO engine can compare two catalog products and solve several useful thresholds while holding the selected scenario constant:

- **product-price break-even** — the highest price option A could cost while matching option B's full TCO;
- **reverse product-price break-even** for option B;
- **electricity-rate break-even** when the two modeled systems consume different amounts of energy;
- **load-hours/day break-even** when the threshold falls inside the selected daily powered-on window.

Example:

```bash
llm-cluster-refresh break-even \
  gpu-nvidia-rtx-3090-24g \
  compute-ryzen-8845hs-32g \
  --price-a 500 \
  --price-b 700 \
  --scenario mixed-3yr
```

The output includes each complete-node BOM/TCO plus the break-even thresholds. Power-derived thresholds inherit the power model's evidence quality: if one side is based on GPU board TGP plus host assumptions, the break-even result is a planning estimate, not a measured energy result.

## Decision integration

The market/model-fit decision score is calculated first. TCO then re-ranks that result using complete-node acquisition and operating cost. This prevents a cheap accelerator from winning solely because its host infrastructure is hidden outside the listing price.

Use:

```bash
llm-cluster-refresh tco --scenario mixed-3yr
llm-cluster-refresh tco --scenario always-on-3yr
llm-cluster-refresh recommendations --scenario high-electricity-3yr
llm-cluster-refresh tco-scenarios
llm-cluster-refresh break-even PART_A PART_B --price-a 500 --price-b 700
```

Autonomous refresh writes `reports/current/daily-tco.md`, `reports/current/daily-tco.json`, and TCO-aware `daily-recommendations.json`.

## Guardrails

- Never hide CPU/host, motherboard, RAM, storage, PSU, chassis, cooling or required interconnect outside a discrete-GPU comparison.
- Never count board TGP/TBP as complete-node measured power.
- Never mix sourced market prices and planning assumptions without labeling each basis.
- Never promote an incomplete/unknown TCO candidate to `Buy` merely because its component price is attractive.
- Keep electricity-rate and usage assumptions user-editable.
- Treat break-even thresholds as scenario-sensitive planning outputs, not forecasts.
