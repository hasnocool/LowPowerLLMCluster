# Ryzen and Rockchip hardware discovery expansion

This catalog expansion adds representative, manufacturer-documented systems for the open Ryzen 7840HS / 8845HS / 8945HS / HX370 and RK3588 / RK3576 discovery goals.

## Ryzen mini PCs

| System | Processor | Board-verified memory | Useful interfaces | Primary source |
|---|---|---:|---|---|
| GMKtec NucBox K6 | Ryzen 7 7840HS / Radeon 780M | 64GB DDR5-5600 | dual 2.5GbE, dual NVMe, USB4 | https://www.gmktec.com/products/amd-ryzen-7-7840hs-mini-pc-nucbox-k6 |
| Beelink SER8 | Ryzen 7 8845HS / Radeon 780M | 256GB DDR5-5600 stated by vendor | 2.5GbE, dual NVMe, USB4 | https://www.bee-link.com/products/beelink-ser8-8845hs |
| MINISFORUM UM890 Pro | Ryzen 9 8945HS / Radeon 780M | 96GB DDR5-5600 | dual 2.5GbE, dual NVMe, dual USB4, OCuLink | https://ca.minisforum.com/products/minisforum-um890pro |
| MINISFORUM AI X1 Pro | Ryzen AI 9 HX 370 / Radeon 890M | 96GB DDR5-5600 | dual 2.5GbE, triple NVMe, dual USB4, OCuLink | https://www.minisforum.com/pages/ai-x1-pro |

The AI X1 Pro page contains inconsistent memory claims: a marketing section says 128GB while the formal product specification table says 96GB. The catalog uses **96GB** until MINISFORUM publishes a consistent specification.

## Rockchip SBCs

| System | SoC | Fixed RAM | Useful interfaces | Primary source |
|---|---|---:|---|---|
| Radxa ROCK 5B+ | RK3588 | 32GB LPDDR5 | 2.5GbE, onboard Wi-Fi 6, dual PCIe 3.0 x2 NVMe | https://docs.radxa.com/en/rock5/rock5b/getting-started/introduction |
| Radxa ROCK 4D | RK3576 | 16GB LPDDR5 | GbE, Wi-Fi 6, UFS/eMMC, PCIe 2.1 x1 expansion | https://docs.radxa.com/en/rock4/rock4d |
| Orange Pi 5 | RK3588S | 32GB LPDDR4X | GbE, M.2 NVMe, GPIO | https://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-5-32GB.html |

These complement the existing Orange Pi 5 Plus 32GB and Radxa ROCK 5 ITX+ 32GB references instead of replacing them.

## Evidence boundaries

This expansion deliberately separates **hardware capability** from **LLM performance and energy evidence**:

- vendor RAM limits are recorded only when the product page or official documentation states them;
- memory capacity is fixed only for soldered LPDDR variants and remains configurable for SO-DIMM mini PCs;
- USB-C/PD/DC adapter ratings are input-capacity facts, not measured complete-node inference power;
- CPU TDP or vendor high-power modes are not copied into `power_target_w`;
- NPU TOPS and GPU marketing scores are not converted into tokens/sec;
- llama.cpp/Vulkan/ROCm/RKNN support remains a runtime-path description until exact device/runtime/model measurements exist;
- current acquisition price remains live-market evidence rather than a static catalog promise.

## Remaining discovery work

The representative CPU/SoC coverage gap is now substantially smaller, but discovery remains open-ended. The next useful additions should be driven by one of three signals: unusually low landed CAD price, unusually high verified memory capacity, or exact measured LLM efficiency that justifies adding another near-duplicate system.
