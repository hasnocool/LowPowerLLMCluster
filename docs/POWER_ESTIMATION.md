# Universal hardware power and Wh estimation

Every hardware category in LowPowerLLMCluster must produce a usable power/energy planning value even when direct wall-power measurements are unavailable.

## Evidence ladder

The estimator now uses the strongest available evidence in this order:

1. direct per-part measured idle + load power;
2. direct measured load/typical power with inferred idle;
3. learned power distribution for the exact SKU/model/configuration;
4. learned hardware-family distribution;
5. published target/TDP/TBP/TGP/board power;
6. published maximum power converted into a conservative typical-load estimate;
7. learned category distribution;
8. category-specific fallback baseline;
9. generic future-category fallback.

Every output keeps `basis`, `confidence`, `inferred`, `power_scope`, warnings, and—when learned evidence is used—the matching distribution.

## Self-improving evidence store

`data/power/evidence.json` is an append-style evidence store consumed by `power_evidence.py`. Observations identify the hardware at the strongest level the source actually supports: exact SKU/model identifier, exact model, hardware family, or category.

Exact configurations may include fixed memory/storage facts. A 64 GB / 2 TB A2485 observation cannot silently become an exact match for a conflicting 32 GB configuration. When several compatible observations exist, the project reports median idle/load power plus p25/p75 load bands and sample counts rather than pretending one benchmark is universal.

Source weighting distinguishes `measured_local`, `vendor_measured`, `community_measured`, manufacturer specifications, and derived estimates. Multiple compatible measured observations can raise confidence; a single family estimate cannot.

Examples of the intended progression are:

```text
Apple silicon category baseline
  -> M1 Max family distribution
  -> A2485 M1 Max distribution
  -> A2485 + 64 GB + 2 TB observations
  -> direct measurement for the exact machine
```

and:

```text
GPU category baseline
  -> RTX 3090 family evidence
  -> RTX 3090 Founders Edition board evidence
  -> exact board + exact host complete-node measurements
```

and:

```text
storage category baseline
  -> NVMe family evidence
  -> exact controller/NAND/SKU observations
```

## Watts versus Wh

Watts describe instantaneous/average power. Wh describe energy over time.

```text
Wh = load_w × load_hours + idle_w × idle_hours + off_w × off_hours
```

TCO reports expose daily Wh/kWh from the selected duty cycle in addition to annual kWh and electricity cost.

## Complete-node modeling

Integrated systems such as mini PCs, Macs, phones and tablets use their device estimate directly.

PCIe/attached accelerators add explicit host idle/load assumptions and PSU/cooling overhead unless a complete-node measurement exists. Once host assumptions are introduced the result remains low confidence; board power is never relabeled as measured wall power.

SBC/dev-board classes add bounded storage/peripheral and conversion overhead. Memory, storage and network components are incremental node loads rather than standalone computers.

## Guardrails

Battery capacity (`Wh`) is stored energy, not consumption. Charger wattage is supply capability, not device power. Neither becomes consumption evidence.

TDP/TBP/TGP/board power is not measured wall input. Learned observations must preserve exact hardware/source provenance, and conflicting exact configurations are rejected rather than averaged.

The goal is complete comparison coverage that improves automatically as real observations accumulate, without erasing the distinction between measurement, published specification, derived estimate, and category fallback.
