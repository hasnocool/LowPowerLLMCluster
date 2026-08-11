# Universal hardware power and Wh estimation

Every hardware category in LowPowerLLMCluster must produce a usable power/energy planning value even when direct wall-power measurements are unavailable.

## Evidence ladder

The estimator uses the strongest available evidence in this order:

1. measured idle + measured load wall/device input power;
2. measured load/typical power with inferred idle;
3. published target/TDP/TBP/TGP/board power;
4. published maximum power converted into a conservative typical-load estimate;
5. category-specific fallback baseline;
6. generic future-category fallback if a new category has not yet been assigned a specific baseline.

Every output keeps `basis`, `confidence`, `inferred`, `power_scope`, and warnings so inferred numbers cannot masquerade as measurements.

## Watts versus Wh

Watts describe instantaneous/average power. Wh describe energy over time.

The estimator therefore keeps power and duty cycle separate:

```text
Wh = load_w × load_hours + idle_w × idle_hours + off_w × off_hours
```

TCO reports now expose `daily_wh` and `daily_kwh` from the selected scenario duty cycle in addition to annual kWh and electricity cost.

## Complete-node modeling

Integrated systems such as mini PCs, Macs, phones and tablets use their device estimate directly.

PCIe/attached accelerators add explicit host idle/load assumptions and PSU/cooling overhead. The resulting complete-node value is always downgraded to low confidence unless a complete-node measurement is supplied; board power is never relabeled as wall power.

SBC/dev-board classes add small storage/peripheral and conversion-overhead assumptions when constructing complete-node power.

Infrastructure categories such as memory, storage and network are modeled as incremental component loads rather than standalone compute nodes.

## Category fallback coverage

Fallbacks currently cover every catalog category:

- compute nodes and mini PCs;
- SBC/dev/embedded/specialty boards;
- control-plane hardware;
- Apple silicon systems;
- phones, tablets and media devices;
- GPU/NPU/TPU/ASIC/FPGA/adaptive-SoC/decommissioned accelerators;
- network hardware;
- memory;
- storage.

Unknown future categories still receive a generic low-confidence baseline instead of returning no energy estimate.

## Guardrails

Battery capacity (`Wh`) is stored energy, not consumption. Charger wattage is a supply capability, not device power. Neither is used as consumption evidence by the fallback estimator.

Manufacturer TDP/TBP/TGP/board-power values are not treated as measured wall input. When they are used, the output remains explicitly inferred and carries the source scope.

The goal is complete comparison coverage without false precision: a low-confidence estimate is preferable to silently dropping a candidate from energy/TCO analysis, but measured evidence always wins when available.
