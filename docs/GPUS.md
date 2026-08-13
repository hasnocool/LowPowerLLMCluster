# Discrete GPU Sourcing

Discrete GPUs are a first-class LowPowerLLMCluster hardware family under `gpu_accelerator`.

They are not treated as an afterthought or collapsed into generic accelerators because GPU-specific buying questions are materially different: fixed VRAM, board-partner SKU variation, PCIe/PSU/cooling requirements, software stack maturity, used-market condition and unusually volatile pricing all matter.

## Why GPUs belong in this catalog

For local LLM work, a used or current discrete GPU can be the best answer when:

- fixed VRAM is large enough for the intended model;
- the runtime/backend is mature on that GPU family;
- board price has fallen enough to beat an integrated/SBC solution;
- host, PSU and cooling costs are acceptable;
- power use is acceptable for the deployment;
- exact-board condition and seller confidence are good enough.

The catalog must therefore source GPUs alongside mini PCs, SBCs, mobile boards, NPUs, TPUs, ASICs and FPGAs.

## Initial GPU families

The first reference set intentionally covers several software ecosystems and both current and used-market candidates:

| Catalog ID | VRAM | Software path | Market role |
|---|---:|---|---|
| `gpu-nvidia-rtx-5060-ti-16g` | 16 GB | CUDA / llama.cpp CUDA | current compact CUDA candidate |
| `gpu-nvidia-rtx-3090-24g` | 24 GB | CUDA / llama.cpp CUDA | used high-VRAM bargain watch |
| `gpu-amd-rx-9070-16g` | 16 GB | ROCm / HIP / Vulkan | current RDNA4 candidate |
| `gpu-amd-rx-9070-xt-16g` | 16 GB | ROCm / HIP / Vulkan | faster but higher-power RDNA4 comparison |
| `gpu-intel-arc-b580-12g` | 12 GB | oneAPI / SYCL / Vulkan | budget Battlemage candidate |
| `gpu-intel-arc-a770-16g` | 16 GB | oneAPI / SYCL / Vulkan | used/discounted 16GB Arc watch |

This is a starting set, not a preferred-brand list.

## Sourcing coverage

GPU names are included in both autonomous market profiles. Structured-market sources can therefore discover exact retail/used listings even when a manufacturer page is only useful as a specification reference.

Official manufacturer/reference URLs live in `data/market/sources.json`. Live seller observations remain separate in `data/market/price-history.json`.

GPU discovery should expand toward:

- additional NVIDIA 12/16/24/32GB generations when market pricing makes them relevant;
- AMD cards with useful VRAM and maintained ROCm/Vulkan paths;
- Intel Arc cards when SYCL/Vulkan pricing is compelling;
- workstation/datacenter GPUs when used/decommissioned prices cross practical thresholds;
- unusual mobile/embedded MXM or compute modules only when host requirements are documented.

## Exact SKU and board-partner rule

A reference GPU identity is not the same thing as an exact add-in-board SKU.

For example, two cards using the same GPU can differ in:

- cooler size and slot width;
- power limit;
- power connectors;
- clock profile;
- warranty;
- physical condition;
- seller history;
- included accessories.

Discovery should preserve the seller's exact title/SKU when available and keep configuration confidence separate from the reference GPU identity.

## VRAM rule

For a discrete GPU, `memory_capacity_gb` means fixed VRAM on that exact GPU variant. It is not host system RAM and it is not expandable.

The model-fit screen can use that fixed VRAM directly for a conservative capacity check. It still must not claim that fitting model weights guarantees runtime success, context size or throughput.

## Power rule

GPU board power is not complete-node power.

Use explicit scopes such as:

- `accelerator_board_tgp`;
- `accelerator_board_tbp`;
- `accelerator_board_power_reference`;
- measured `complete_node_input` only when the whole host is actually measured.

A 180W GPU and a 180W complete computer are not equivalent. Decision reports may use board power as deployment friction, but not as canonical tokens/joule.

## Software maturity

GPU recommendations should account for software reality rather than vendor peak compute claims.

Typical paths include:

- NVIDIA: CUDA, llama.cpp CUDA, PyTorch/CUDA runtimes;
- AMD: ROCm/HIP where supported plus Vulkan paths;
- Intel: oneAPI/SYCL, Vulkan, OpenVINO and supported PyTorch extensions.

TOPS, TFLOPS, shader counts and memory bandwidth are useful specifications but must never be converted directly into tokens/sec.

## Used-market GPU risk

Used GPUs deserve additional attention to:

- seller confidence;
- cooling/fan condition;
- corrosion or physical damage;
- modified BIOS/firmware;
- prior high-load use;
- connector/cable requirements;
- return policy;
- price history and reappearance behavior.

These factors belong in market evidence and confidence, not in the immutable GPU reference identity.

## Decision-report integration

GPUs participate in the same `Buy / Watch / Ignore / Experimental` decision engine as other LLM candidates.

For GPUs, the strongest decision inputs are:

1. live/current price position versus observed history;
2. fixed VRAM capacity/model fit;
3. SKU and seller confidence;
4. software maturity and risk;
5. opportunity freshness;
6. host/PSU/cooling friction.

The decision engine does not award synthetic performance points from GPU TOPS/TFLOPS.
