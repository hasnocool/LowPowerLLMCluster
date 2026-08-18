# Workstation and datacenter GPU deal watches

This layer watches high-VRAM workstation and legacy datacenter GPUs without promoting them into the canonical catalog merely because a marketplace listing exists.

## Why this is separate from the canonical GPU catalog

The project already has exact-SKU promotion gates, source confidence, compatibility solving and evidence history. Workstation/datacenter cards are especially sensitive to board identity, cooling, power connectors, host compatibility, seller condition and software/runtime support. A cheap listing is therefore a **discovery event**, not proof that the hardware belongs in the canonical recommendation set.

The focused `gpu-deal-scan` profile searches structured eBay results daily and lets existing promotion/evidence machinery decide whether an exact listing should advance further.

## Absolute landed-CAD deal thresholds

Watchlists can now set `alerts.max_landed_cad`. The intelligence pipeline emits a `deal_threshold` alert when:

1. a matching listing is first observed at or below the configured landed-CAD ceiling; or
2. an existing listing crosses from above the ceiling to at/below it.

Repeated observations that remain below the ceiling are not emitted repeatedly. The normal alert fingerprint state still prevents duplicate delivery after restart.

The default ceilings are intentionally policy values, not claims about fair market value:

| Watch | Matching families | Default ceiling | Intent |
|---|---|---:|---|
| `workstation-gpu-24gb-deal` | RTX A5000, Arc Pro B60 | CA$900 landed | Review a 24GB professional card when its complete acquisition price competes with consumer high-VRAM alternatives. |
| `workstation-gpu-32gb-deal` | Radeon Pro W6800, Arc Pro B65/B70 | CA$1,200 landed | Surface 32GB cards only when the extra VRAM is available at a meaningfully constrained acquisition cost. |
| `workstation-gpu-48gb-deal` | RTX A6000, Quadro RTX 8000 | CA$1,800 landed | Flag 48GB cards when they enter a range worth comparing against multi-GPU or high-memory unified-memory systems. |
| `legacy-datacenter-24gb-deal` | Tesla P40 | CA$350 landed | Keep older datacenter hardware experimental and require a much lower purchase price to offset cooling, integration and software risk. |

These values are meant to be edited as Canadian pricing, exchange rates, electricity costs and competing hardware change.

## Manufacturer evidence used to define the watch scope

The watch names are based on official manufacturer product families and published hardware characteristics. They are not benchmark claims.

- Intel Arc Pro B50: Intel lists 16GB GDDR6, 224 GB/s memory bandwidth, PCIe 5.0 x8 and 70W TBP: https://www.intel.com/content/www/us/en/products/sku/242615/intel-arc-pro-b50-graphics/specifications.html
- Intel Arc Pro B60/B65/B70 family: Intel publishes 24GB for B60 and 32GB for B65/B70, with Linux multi-GPU positioning and oneAPI/OpenVINO support: https://www.intel.com/content/www/us/en/products/details/discrete-gpus/arc/workstations/b-series.html
- NVIDIA RTX A5000: NVIDIA publishes 24GB GDDR6 ECC, PCIe Gen4 x16 and 230W board power: https://www.nvidia.com/en-us/design-visualization/rtx-a5000/
- NVIDIA RTX A6000: NVIDIA publishes 48GB GDDR6 ECC, PCIe Gen4 x16 and 300W maximum power: https://www.nvidia.com/en-us/design-visualization/rtx-a6000/
- AMD Radeon Pro W6800: AMD publishes 32GB GDDR6 ECC, PCIe 4.0 x16, 512 GB/s bandwidth and 250W TBP: https://www.amd.com/en/products/graphics/workstations/radeon-pro/w6800.html

The Tesla P40 and Quadro RTX 8000 remain legacy/secondary-market watch terms. Exact board, memory, connector, firmware and runtime evidence must still be verified from the listing and authoritative product documentation before promotion.

## Scheduling and API budget

`gpu-deal-scan` is intentionally narrow:

- source: eBay Browse adapter only;
- nine exact family queries;
- separate per-run and daily request budget;
- automatic Bank of Canada FX refresh for USD/EUR/GBP;
- no BOM refresh or power-evidence refresh in this focused pass;
- normal report, alert-priority and recommendation generation after ingestion.

This keeps the GPU watch responsive without consuming the query budget reserved for the broader daily and weekly discovery profiles.

## Evidence boundary

A threshold alert means only: **this observed listing is cheap enough to investigate now**.

It does not mean:

- the listing is authentic;
- the GPU is in good condition;
- the card fits an owned host;
- the runtime works for the intended model;
- board TGP/TBP equals complete-node wall power; or
- the product should be promoted into the canonical catalog.

Those decisions stay behind the existing exact-identity, compatibility, condition, performance and promotion gates.
