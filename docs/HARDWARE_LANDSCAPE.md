# Hardware Landscape

The catalog does not assume one architecture wins. It tracks products that may be useful for different budgets, model sizes and workloads.

```text
                                HARDWARE CATALOG
                                      │
      ┌───────────────┬───────────────┼──────────────┬────────────────┐
      ▼               ▼               ▼              ▼                ▼
 low-power x86     ARM/SBCs       GenAI NPU/TPU   specialist AI    FPGA / EOL
 Ryzen / N100    RK3588/Jetson   Hailo/SOPHGO    Coral/MemryX     Kria/Alveo
      │               │               │              │                │
      └───────────────┴───────────────┼──────────────┴────────────────┘
                                      ▼
                            PRICE + SPECS + SOFTWARE
                                      │
                             evidence/confidence
                                      │
                                      ▼
                               BUYING SHORTLIST
```

## What each class is trying to answer

### Mobile x86 / mini PCs

How much useful RAM, Linux compatibility and upgradeability can we get per dollar and watt class?

### RK3588 / ARM SBCs

Can 16-32GB compact nodes offer an attractive always-on or small-model option at very low power?

### Jetson

Does the mature CUDA/TensorRT ecosystem justify the memory/price limits for small LLM/VLM and multimodal use?

### AMD BC-250 and similar oddities

Does unusually cheap unified high-bandwidth memory outweigh difficult software, cooling and lifecycle risk?

### GenAI NPU / TPU

Is there a real transformer runtime, enough model memory, reasonable host cost and compelling low-power use case?

### Fixed-function specialist accelerators

Can cheap low-watt vision/audio hardware save whole-system energy by letting a general worker stay asleep?

### FPGA / adaptive / decommissioned

Does secondary-market price or programmability make the engineering burden worthwhile? These are valid catalog/watch items even before a project benchmark exists.

## The anti-trap

```text
      impressive specification
               │
               ▼
         interesting candidate
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
    price    memory   runtime
       │       │        │
       └───────┼────────┘
               ▼
      useful catalog record
               │
       performance evidence?
          │ yes      │ no
          ▼          ▼
      cite source   show unknown
          │          │
          └────┬─────┘
               ▼
         buying decision
```

A benchmark can improve confidence later. It is not required for the product to be worth tracking.
