# Hardware Landscape

The project does not assume one architecture wins. It looks for **specialists** that combine well.

```text
                                  LLM CLUSTER
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
       ▼                               ▼                               ▼
 ALWAYS-ON CONTROL                 GENERAL WORKERS                SPECIALISTS
       │                               │                               │
 Intel N100                     Ryzen U/HS mini PCs              BC-250
 ~very low power                32-96GB DDR5                     16GB GDDR6
 routing/metrics                broad Linux support              cheap bandwidth
       │                               │                               │
       │                         RK3588 32GB SBC                  Jetson Orin
       │                         low-power ARM                    CUDA / vision
       │                               │                               │
       └───────────────────────────────┼───────────────────────────────┘
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

### High-core mobile-CPU motherboards

Can a 16-core laptop CPU on a standard board, power-capped aggressively, provide a better heavy-CPU worker than multiple smaller nodes?

## The anti-trap

Do not pick winners from specifications alone.

```text
      impressive spec
           │
           ▼
   "448 GB/s!" / "67 TOPS!"
           │
           ▼
      NOT A WINNER YET
           │
           ▼
   same model + same runtime
   + measured wall power
           │
           ▼
   tokens/s + tokens/joule
           │
           ▼
       useful evidence
```
