# Project Charter

## Mission

Find, measure and combine unusually cost-effective hardware into a low-power distributed local-LLM inference system. The project is intentionally broader than laptop motherboards: any hardware is eligible if it may offer compelling **usable model capacity, measured inference throughput, energy efficiency, acquisition cost or cluster density**.

## Hardware in scope

- laptop/mobile-CPU motherboards
- mini PCs and barebones
- SBCs and ARM development boards
- embedded/industrial boards
- edge-AI developer kits
- decommissioned or specialty compute boards such as AMD BC-250
- NPUs, TPUs and AI ASICs with usable model/runtime paths
- FPGAs and adaptive SoCs for custom low-precision/transformer research
- decommissioned accelerators when secondary-market value may justify software/integration risk
- fixed-function accelerators when they improve whole-cluster efficiency by offloading specialist workloads
- ultra-low-power control-plane nodes
- networking, memory, storage and DC-power infrastructure required by the cluster

## North-star measurements

A platform is valuable only after we can answer:

1. What models actually fit?
2. What prompt and generation throughput does it deliver?
3. How many watts does the complete node consume at idle, prefill and decode?
4. What are tokens/joule and tokens/$?
5. How difficult is it to deploy and maintain?
6. What does a useful cluster built from it cost and consume?

Marketing TOPS, core counts and advertised TDPs are discovery signals, not final rankings.

## Non-goals

- chasing maximum benchmark performance regardless of energy/cost
- pretending heterogeneous nodes combine into one fast memory pool over ordinary Ethernet
- presenting seller claims as verified specifications
- recommending unstable firmware modifications as normal setup steps
- optimizing for gaming instead of inference
