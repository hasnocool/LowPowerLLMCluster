# Project Charter

## Mission

Build the most useful practical **catalog and buying/research planner** for low-power local-LLM hardware: mini PCs, mobile-CPU boards, SBCs, dev kits, embedded boards, NPUs/TPUs/ASICs, FPGAs, specialty systems and unusual/decommissioned accelerators.

The project should answer: **What can I buy, what does it cost, what can it probably fit/run, how difficult is it to use, how efficient might it be, how strong is the evidence, and is it a good deal?**

Owning every product is neither expected nor required.

## Primary product

1. Product catalog with current URLs/prices and exact configuration notes.
2. Hardware/software specifications with provenance.
3. Model-capacity screens and compatibility notes.
4. Confidence-labelled vendor/community/local performance evidence when available.
5. Buying-oriented filters, rankings, BOMs and price history.
6. Optional benchmark tooling for hardware contributors actually possess.

## Hardware in scope

- laptop/mobile-CPU motherboards and mini PCs/barebones
- SBCs, ARM development boards and embedded/industrial systems
- edge-AI developer kits and specialty compute such as AMD BC-250
- NPUs, TPUs, AI ASICs, FPGAs and adaptive SoCs
- decommissioned accelerators when used pricing may justify integration risk
- fixed-function vision/audio/embedding accelerators as specialist offload
- control-plane nodes, networking, memory, storage and power infrastructure

## North-star catalog questions

For every candidate, try to answer:

1. What exact product/configuration is being referenced?
2. What is the current price and source date?
3. Is RAM included/fixed, configurable, or merely a CPU theoretical maximum?
4. What models are plausible capacity candidates?
5. What runtime/backend is available and how mature is it?
6. What power number is known, and what boundary does it describe?
7. Is there vendor/community/local measured performance evidence?
8. How confident are those claims?
9. What extra host, PSU, cooling, storage or adapters are required?
10. Is the product still a good buy after those costs and risks?

## Optional measurement role

The benchmark harness exists to add higher-quality evidence when a contributor owns hardware or imports a reproducible result. It is **not** the project's main purpose and must never block catalog growth.

## Non-goals

- pretending specifications can simulate exact tokens/sec
- requiring physical ownership before cataloging hardware
- turning the project into a benchmark lab at the expense of product discovery
- presenting seller/community claims as manufacturer facts
- treating heterogeneous Ethernet nodes as one fast memory pool
