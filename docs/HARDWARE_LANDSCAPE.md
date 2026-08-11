# Hardware Landscape

The project does not assume one architecture wins. It looks for **specialists** that combine well.

```text
                                      LLM / AI CLUSTER
                                             │
        ┌────────────────────┬───────────────┼───────────────┬────────────────────┐
        │                    │               │               │                    │
        ▼                    ▼               ▼               ▼                    ▼
 ALWAYS-ON CONTROL      GENERAL WORKERS    GenAI NPU/TPU   SPECIALIST AI      RESEARCH / EOL
        │                    │               │               │                    │
 Intel N100            Ryzen U/HS        Hailo-10H       Coral TPU          AMD Kria FPGA
 routing/metrics        32-96GB DDR5      SOPHGO BM1688   MemryX MX3         Versal adaptive
                                             │               │               Alveo U50/V70
                       RK3588 / Jetson     BM1684X         vision/audio       legacy VPUs
                       BC-250 oddities     Tenstorrent      offload                │
        │                    │               │               │                    │
        └────────────────────┴───────────────┼───────────────┴────────────────────┘
                                             ▼
                                    WORKLOAD-AWARE ROUTER
```

## What each class is trying to prove

### Mobile x86 / mini PCs

Can commodity laptop silicon provide the best balance of RAM capacity, Linux compatibility, price and power?

### RK3588 / high-memory SBCs

Can a 24-32GB ARM node stay useful at very low idle/load power while remaining cheap enough to deploy densely?

### Jetson

Does a mature accelerator stack beat general-purpose hardware for small LLM, VLM, embedding and multimodal workloads even when RAM capacity is limited?

### AMD BC-250 and similar oddities

Can decommissioned or non-mainstream hardware expose unusually cheap unified memory bandwidth that compensates for difficult software and hardware integration?

### GenAI NPU / TPU

Can dedicated small-model hardware such as Hailo-10H or SOPHGO BM1688 deliver better sustained tokens/joule than a general CPU/GPU node once the host, model conversion and memory ceiling are included?

### AI ASIC

Can purpose-built AI processors such as Tenstorrent provide a better scaling architecture through local accelerator memory and high-speed interconnect even when their absolute board power is much higher than the project's normal worker target?

### Fixed-function specialist accelerators

Can Coral/MemryX-class devices lower **whole-cluster** energy by taking over continuous vision or other fixed inference and letting larger LLM workers sleep?

### FPGA / adaptive SoC

Can a custom datapath for INT4, ternary/BitNet, sparse operations, KV-cache movement or other transformer-specific work beat commodity hardware per watt? Stock vision-DPU performance does not answer this question.

### Decommissioned accelerators

Can enterprise hardware become attractive after liquidation once used price, driver/toolchain survival, replacement availability and integration burden are included?

## The anti-trap

Do not pick winners from specifications alone.

```text
        impressive spec
             │
             ▼
  "448 GB/s" / "404 TOPS"
             │
             ▼
        NOT A WINNER YET
             │
             ▼
 runtime supports workload?
       │ yes       │ no
       ▼           └────> specialist/unusable for that task
 model fits memory?
       │ yes
       ▼
 same workload + complete-node power
       │
       ▼
 tokens/s + tokens/joule + reliability
       │
       ▼
         useful evidence
```
