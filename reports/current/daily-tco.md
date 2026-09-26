# Complete-Node Total Cost of Ownership

Scenario: **mixed-3yr**
Ownership: **new-build**

Product price is separated from incremental infrastructure and electricity. Power uses measured/published evidence when available and conservative inferred fallbacks otherwise.

Decision | Score | Product | Missing infra | Sourced lines | Avoided owned cost | Wh/day | Complete node | Operating | TCO | Candidate
--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 354 | — | CA$58 | — | Beelink SER8, Ryzen 7 8845HS
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 355 | — | CA$58 | — | Framework Laptop 13 Mainboard, Ryzen AI 5 340
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 354 | — | CA$58 | — | GMKtec NucBox K6, Ryzen 7 7840HS
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 354 | — | CA$58 | — | MINISFORUM AI X1 Pro, Ryzen AI 9 HX 370
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 695 | — | CA$114 | — | MINISFORUM BD795M motherboard with Ryzen 9 7945HX
Watch | 49.4 | — | CA$450 | 0 | CA$0 | 354 | — | CA$58 | — | MINISFORUM UM890 Pro, Ryzen 9 8945HS
Watch | 46.8 | — | CA$850 | 0 | CA$0 | 4,348 | — | CA$714 | — | NVIDIA GeForce RTX 3090 24GB
Watch | 46.2 | — | CA$450 | 0 | CA$0 | 486 | — | CA$80 | — | Ryzen AI 9 HX 370 barebone, DDR5, dual LAN, OCuLink, Wi-Fi 7
Watch | 46.2 | — | CA$450 | 0 | CA$0 | 486 | — | CA$80 | — | Topton FU05 Ryzen 7 8745HS barebone, dual 2.5GbE, 2x DDR5, 2x NVMe, OCuLink
Watch | 45.5 | — | CA$450 | 0 | CA$0 | 486 | — | CA$80 | — | Ryzen 7 7735U DDR5 mini PC / barebone
Watch | 45.3 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple Mac Studio (M1 Max / M1 Ultra, 2022)
Watch | 45.3 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple Mac Studio (M4 Max / M3 Ultra, 2025)
Watch | 45.3 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple MacBook Pro 14/16-inch (M5 Pro / M5 Max, 2026)
Watch | 45.3 | — | CA$350 | 0 | CA$0 | 151 | — | CA$25 | — | Turing RK1 compute module, RK3588, 32GB
Watch | 40.0 | — | CA$850 | 0 | CA$0 | 2,850 | — | CA$468 | — | NVIDIA GeForce RTX 5060 Ti 16GB
Watch | 38.0 | — | CA$850 | 0 | CA$0 | 3,202 | — | CA$526 | — | AMD Radeon RX 9070 16GB
Watch | 38.0 | — | CA$850 | 0 | CA$0 | 3,943 | — | CA$648 | — | AMD Radeon RX 9070 XT 16GB
Watch | 38.0 | — | CA$850 | 0 | CA$0 | 3,246 | — | CA$533 | — | Intel Arc A770 16GB
Watch | 38.0 | — | CA$850 | 0 | CA$0 | 2,938 | — | CA$483 | — | Intel Arc B580 12GB
Watch | 37.8 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple Mac mini (M4 / M4 Pro, 2024)
Watch | 37.8 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple MacBook Air 13/15-inch (M5, 2026)
Watch | 37.8 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple MacBook Pro 14-inch (M5, 2025)
Watch | 37.8 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple MacBook Pro 14/16-inch (M1 Pro / M1 Max, 2021)
Watch | 37.8 | — | CA$0 | 0 | CA$0 | 396 | — | CA$65 | — | Apple iMac 24-inch (M4)
Experimental | 44.6 | — | CA$850 | 0 | CA$0 | 3,907 | — | CA$642 | — | Tenstorrent Blackhole p150, 32GB GDDR6
Experimental | 44.6 | — | CA$850 | 0 | CA$0 | 3,907 | — | CA$642 | — | Tenstorrent Wormhole n300s, 24GB GDDR6
Experimental | 37.0 | — | CA$850 | 0 | CA$0 | 2,674 | — | CA$439 | — | Tenstorrent Wormhole n150s PCIe accelerator
Experimental | 35.9 | — | CA$350 | 0 | CA$0 | 695 | — | CA$114 | — | AMD / ASRock BC-250 specialty compute board, 16GB unified GDDR6
Ignore | 44.6 | — | CA$0 | 0 | CA$0 | 58 | — | CA$9 | — | ASUS ROG Phone 9 Pro Edition, 24GB / 1TB
Ignore | 44.6 | — | CA$850 | 0 | CA$0 | 2,850 | — | CA$468 | — | FuriosaAI RNGD PCIe accelerator, 48GB HBM3

- Wh/day uses the selected scenario duty cycle, not the hardware power rating alone.
- Measured power is preferred; published target/max values are next; category inference is the final fallback.
- Battery capacity and charger wattage are not treated as device consumption.
- Missing infra = only components that must still be purchased.
- Ownership changes acquisition cost, not the complete-node power model.
