# High-RAM Android inference nodes

Catalog evidence refreshed: **2026-08-17**.

LowPowerLLMCluster treats Android phones and tablets as **mobile inference endpoints**, not miniature replacements for normal Linux or macOS service nodes.

The useful Android candidates are the devices that combine enough physical RAM for local model capacity with a plausible native/Vulkan runtime path and market availability that can become attractive as devices depreciate.

## Current high-RAM references

The canonical mobile catalog now includes these exact high-memory configurations:

| Device | RAM | SoC | Why it is tracked | Official evidence |
|---|---:|---|---|---|
| OnePlus 15 16GB / 512GB | 16GB LPDDR5X Ultra+ | Snapdragon 8 Elite Gen 5 | Current North American flagship with 16GB fixed RAM and an Android/Vulkan experimentation path. | https://www.oneplus.com/ca_en/15/specs |
| Xiaomi 15 Ultra 16GB | 16GB LPDDR5X | Snapdragon 8 Elite | Useful 16GB reference with 512GB/1TB storage variants and likely future used-market relevance. | https://www.mi.com/global/product/xiaomi-15-ultra/specs/ |
| REDMAGIC 11 Pro 24GB / 1TB | 24GB LPDDR5T | Snapdragon 8 Elite Gen 5 | Unusually large phone RAM plus an active liquid/fan cooling system; worth measuring for sustained local inference. | https://global.redmagic.gg/pages/redmagic-11-pro-specs |
| ASUS ROG Phone 9 Pro Edition 24GB / 1TB | 24GB LPDDR5X | Snapdragon 8 Elite | High-capacity gaming phone likely to become more interesting as used prices fall. | https://rog.asus.com/phones/rog-phone-9-pro/spec/ |
| Samsung Galaxy Tab S11 Ultra 16GB / 1TB | 16GB | MediaTek Dimensity 9400+ | Large Android tablet with more physical thermal area and expandable storage; useful interactive endpoint. | https://news.samsung.com/ca/meet-samsung-galaxy-tab-s11-series-packing-everything-you-expect-from-a-premium-tablet |

Existing Pixel 10 Pro / Pro XL and Galaxy S26 Ultra references remain in the catalog.

## Runtime policy

Android is handled differently from iOS/iPadOS in `mobile_platform.mobile_runtime_profile()`.

For an Android phone or tablet whose catalog software stack records an Android native/app-local runtime path:

- `local_cli=true` because native/terminal-style local execution is feasible on Android;
- `vulkan=true` only when Vulkan is explicitly included in the software-stack evidence;
- `headless_service=false` and `persistent_daemon=false` because the project does not assume unrestricted unattended background execution;
- phone thermal constraint remains `high`;
- tablet thermal constraint remains `medium_high`;
- shared-memory capacity remains subject to the same conservative mobile reserve used by model-fit screening.

This is a **deployment-capability classification**, not a throughput claim. A runtime still needs to be validated on the exact Android build, GPU driver and backend before a benchmark is accepted.

## Memory policy

These entries represent exact high-RAM configurations rather than family maxima. That lets model-fit screening use real installed capacity.

The default mobile reserve keeps 40% of installed RAM unavailable to the model for OS, graphics, runtime and workload overhead. For example:

- 16GB installed -> 9.6GB conservative model-fit budget;
- 24GB installed -> 14.4GB conservative model-fit budget.

The reserve is intentionally conservative and is not a performance prediction.

## Used-market policy

Catalog inclusion does not create a static fair-market price. The new entries use `live_market_required` pricing and marketplace-watch listing states so price evidence can be attached when observed.

A used Android device should be evaluated with:

- exact RAM/storage configuration;
- device and battery condition where the marketplace exposes it;
- seller and return-policy evidence;
- current landed-CAD cost;
- runtime/backend compatibility;
- sustained thermal behavior;
- measured inference throughput and power only when exact-device evidence exists.

The catalog does not treat a gaming-phone MSRP, charger rating, battery size, gaming benchmark or marketing AI score as local-LLM value.

## Power boundary

Battery capacity and fast-charging wattage are not inference wall-input power. The mobile catalog intentionally does not populate `power_target_w` from charging specifications.

Complete-device idle/load/inference power should be added only through the sourced power-evidence pipeline with exact device, runtime, workload and measurement-boundary provenance.

## Follow-up evidence

The highest-value next measurements are exact-device llama.cpp/MLC/native Android throughput plus complete-device power for the 24GB gaming phones and the 16GB tablet. Those remain evidence-harvesting tasks until reproducible sources or local measurements are available.
