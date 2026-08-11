# Complete-Node Total Cost of Ownership

The project compares **usable systems**, not isolated sticker prices.

A CA$500 GPU is not a CA$500 inference node when it still needs a host, RAM, storage, PSU, PCIe/OCuLink hardware, cooling and chassis support. Likewise, a barebone mini PC may need RAM/storage before it is comparable with a complete system.

## Cost stack

```text
product/listing price
        │
        ├── host platform
        ├── host/system RAM
        ├── storage
        ├── PSU / power supply
        ├── PCIe / OCuLink / riser
        ├── carrier board when required
        ├── cooling
        └── chassis / miscellaneous integration
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

`data/market/tco-scenarios.json` contains **planning assumptions**, not live quotations. Replace those defaults with locally sourced costs before making a purchase decision.

## Deployment profiles

The TCO engine infers a conservative deployment profile from catalog metadata:

- `complete_system` — product is treated as usable without a separate host stack;
- `barebone_or_board` — adds RAM, storage, power, cooling and chassis assumptions;
- `host_attached_pcie` — adds host, host RAM, storage, PSU, PCIe adapter, cooling and chassis;
- `host_attached_usb` — adds the host platform needed to make a USB accelerator useful;
- `module_requires_carrier` — adds a carrier board and supporting infrastructure;
- `standalone_board` — adds storage/power/cooling/chassis planning costs.

These profiles should become more exact as catalog records gain explicit included-component evidence.

## Power evidence boundaries

Power remains provenance-sensitive.

A GPU's TBP/TGP is **not** complete-node wall power. When only board power exists, the planning model creates a low-confidence complete-node estimate by adding explicit host idle/load assumptions plus PSU/cooling overhead. The result is labeled:

`estimated_complete_node_from_board_power_plus_host_assumptions`

It must never be presented as measured tokens/joule or measured wall input.

A real `complete_node_input` measurement remains the preferred evidence for final efficiency comparisons.

## Operating scenarios

The shipped scenarios cover occasional, mixed, always-on and higher-electricity sensitivity cases. Each scenario records:

- load hours/day;
- idle hours/day;
- days/year;
- CAD/kWh assumption;
- ownership years.

The defaults are deliberately editable. They are planning examples, not a claim about the user's electricity tariff.

## Decision integration

The market/model-fit decision score is calculated first. TCO then re-ranks that result using complete-node acquisition and operating cost.

This prevents a cheap accelerator from winning solely because its host infrastructure is hidden outside the listing price. Missing TCO evidence also prevents a candidate from being promoted to `Buy` purely on a partial sticker price.

Use:

```bash
llm-cluster-refresh tco --scenario mixed-3yr
llm-cluster-refresh tco --scenario always-on-3yr
llm-cluster-refresh recommendations --scenario high-electricity-3yr
llm-cluster-refresh tco-scenarios
```

Autonomous refresh writes:

- `reports/current/daily-tco.md`
- `reports/current/daily-tco.json`
- TCO-aware `daily-recommendations.json`

## Guardrails

- Never hide required host infrastructure outside the comparison.
- Never count board TGP/TBP as complete-node measured power.
- Never mix sourced market prices and planning assumptions without labeling each basis.
- Never promote an incomplete/unknown TCO candidate to `Buy` merely because its component price is attractive.
- Keep electricity-rate and usage assumptions user-editable.
