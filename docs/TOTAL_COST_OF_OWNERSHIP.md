# Complete-Node Total Cost of Ownership

The project compares **usable systems**, not isolated sticker prices.

A CA$500 GPU is not a CA$500 inference node when it still needs a CPU/host, motherboard, RAM, storage, PSU, PCIe/OCuLink hardware, cooling and chassis. The ownership-aware layer then asks which of those required parts are already owned and compatible, so they are not purchased twice.

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
required complete-node BOM
      │
      ├── already owned → CA$0 incremental acquisition
      └── missing       → purchase assumption / sourced price
      │
      ▼
incremental acquisition cost
      │
      +
complete-node idle/load energy scenario
      │
      ▼
total cost of ownership
```

`data/market/tco-scenarios.json` contains planning assumptions, not live quotations. Component lines stay separate so each can later be replaced independently with sourced local prices.

## Ownership profiles

The shipped ownership profiles are:

- `new-build` — buy every infrastructure component required by the deployment profile;
- `reuse-host-core` — reuse CPU/host, motherboard, RAM, storage and chassis; still buy missing PSU, PCIe integration and cooling when required;
- `reuse-complete-host` — reuse a compatible complete host including PSU and cooling; normally only accelerator-specific integration remains;
- `reuse-everything` — every required infrastructure component is already owned and compatible; only the listed product is new acquisition cost.

You can also add arbitrary owned components on top of a named profile.

Examples:

```bash
# Full new GPU build
llm-cluster-refresh tco --scenario mixed-3yr --ownership new-build

# Existing desktop, but it may still need PSU/cooling/adapter upgrades
llm-cluster-refresh tco --scenario mixed-3yr --ownership reuse-host-core

# Existing host plus an already-owned 750W PSU
llm-cluster-refresh tco \
  --scenario mixed-3yr \
  --ownership reuse-host-core \
  --owned psu_750w

# Existing complete compatible PC; only accelerator integration is incremental
llm-cluster-refresh tco --ownership reuse-complete-host
```

Owned components are recorded with basis `already_owned`, a zero incremental acquisition cost, and the planning-reference cost they avoided. **Ownership never removes those parts from the power model.** Reusing a CPU/motherboard/RAM stack lowers acquisition cost, but the powered host still consumes electricity.

## Deployment profiles

The TCO engine separately infers what a product needs to become usable:

- `complete_system` — no separate host stack;
- `barebone_or_board` — RAM, storage, power, cooling and chassis as needed;
- `host_attached_pcie` — CPU/host, motherboard, RAM, storage, PSU, PCIe integration, cooling and chassis;
- `host_attached_usb` — CPU/host, motherboard, RAM, storage, power and chassis;
- `module_requires_carrier` — carrier board and supporting infrastructure;
- `standalone_board` — storage/power/cooling/chassis planning costs.

Deployment profile answers **what is required**. Ownership profile answers **which required parts must actually be bought**.

## Power evidence boundaries

A GPU's TBP/TGP is not complete-node wall power. When only board power exists, the planning model creates a low-confidence complete-node estimate by adding explicit host idle/load assumptions plus PSU/cooling overhead. Already owning the host does not change this power estimate.

`estimated_complete_node_from_board_power_plus_host_assumptions`

A real `complete_node_input` measurement remains the preferred evidence for final efficiency comparisons.

## Break-even analysis

Break-even comparisons can use a different ownership profile on each side. This matters when comparing, for example, a GPU that can reuse an existing desktop against a new integrated node.

```bash
llm-cluster-refresh break-even \
  gpu-nvidia-rtx-3090-24g \
  compute-ryzen-8845hs-32g \
  --price-a 500 \
  --price-b 700 \
  --ownership-a reuse-host-core \
  --ownership-b new-build \
  --scenario mixed-3yr
```

The output includes each option's incremental infrastructure, avoided acquisition from already-owned parts, complete-node acquisition, operating cost, TCO, product-price break-even, and power-sensitive break-even thresholds.

## Guardrails

- Never charge twice for compatible hardware the user already owns.
- Never make already-owned hardware disappear from operating-power calculations.
- Never assume owned hardware is compatible merely because it exists; ownership profiles represent a planning scenario, not automatic compatibility proof.
- Never hide CPU/host, motherboard, RAM, storage, PSU, chassis, cooling or required interconnect outside a discrete-GPU comparison.
- Never count board TGP/TBP as complete-node measured power.
- Never mix sourced market prices and planning assumptions without labeling each basis.
- Keep electricity-rate, usage and ownership assumptions user-editable.
- Treat break-even thresholds as scenario-sensitive planning outputs, not forecasts.
