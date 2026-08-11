# Accelerator Landscape

LowPowerLLMCluster treats accelerators as **specialists**, not magical replacements for CPUs and GPUs. The useful question is not "how many TOPS?" It is:

> **Is this exact product worth tracking or buying for a real workload, given its memory, runtime, price, host requirements, power scope and evidence quality?**

## The expanded accelerator map

```text
                           AI ACCELERATOR DISCOVERY
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
        LLM-CAPABLE            SPECIALIST AI          RESEARCH / EOL
              │                     │                     │
      Hailo-10H NPU           Coral Edge TPU          AMD Kria FPGA
      SOPHGO BM1688           MemryX MX3 NPU          Versal adaptive SoC
      BM1684X TPU             Hailo-8 class           Alveo V70 EOL
      Tenstorrent ASIC        vision inference        old Movidius VPUs
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    ▼
                         WORKLOAD-AWARE ROUTER
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
     text generation          camera / vision          experiments
      LLM / VLM                fixed models           custom datapaths
```

## Why this matters

A heterogeneous cluster can reduce average power by sending work to the smallest device that actually supports it.

```text
       incoming task
            │
            ▼
   ┌──────────────────┐
   │ What workload is │
   │ this really?     │
   └────────┬─────────┘
            │
     ┌──────┼──────────────┐
     │      │              │
     ▼      ▼              ▼
  vision   small LLM     large LLM
     │      │              │
     ▼      ▼              ▼
 Coral /  Hailo-10H /   Ryzen / BC-250 /
 MemryX   SOPHGO        bigger accelerator
```

A 2W vision TPU that cannot run an LLM can still improve the **whole cluster** if it keeps the 30W or 100W inference node asleep.

## Families

### NPU

Examples: Hailo-10H and MemryX MX3.

NPUs are purpose-built neural processors. Their usefulness depends heavily on the compiler/runtime and model memory architecture. Hailo-10H is especially important because it adds dedicated memory and an explicit generative-AI path; MX3 is tracked mainly as a streaming-vision specialist.

### TPU

Examples: SOPHGO BM1684X/BM1688 and Google Coral Edge TPU.

"TPU" does not imply one common programming model. SOPHGO's current LLM-TPU stack makes BM1684X/BM1688 genuine transformer candidates. Coral remains a fixed INT8 TensorFlow Lite specialist and should not be ranked as a general LLM worker.

### AI ASIC

Example: Tenstorrent Wormhole.

Purpose-built AI ASICs can offer model-oriented memory/interconnect designs that commodity Ethernet clusters cannot reproduce. Wormhole is too power-hungry to be a normal low-power node, but its open software stack and 400GbE-class accelerator links make it a valuable performance/scaling reference.

### FPGA and adaptive SoC

Examples: AMD Kria and Versal.

These are research platforms. Their advantage is **programmability**: we can potentially build datapaths for INT4, ternary/BitNet weights, sparse operations, custom KV-cache movement or other transformer-specific work. Their stock vision DPU numbers must not be treated as LLM performance.

### Decommissioned accelerators

Examples: AMD Alveo V70 and Intel Neural Compute Stick 2.

Discontinued hardware can become attractive when enterprise inventory is liquidated. The catalog therefore supports unresolved prices and lifecycle state explicitly. A discontinued accelerator can remain a catalog/watch item with unknown performance. For a strong purchase recommendation, prefer evidence that:

1. a real current acquisition price exists;
2. the software stack is still installable and reproducible;
3. a relevant transformer or specialist workload runs;
4. power scope is understood (measured complete-system power is ideal when available);
5. the value plausibly beats simpler hardware after integration cost is included.

## The TOPS trap

```text
         404 TOPS
            │
            ▼
       sounds huge
            │
            ▼
      NOT A RESULT
            │
            ▼
 model compiles? ── no ──> unusable for that workload
      │ yes
      ▼
 model fits memory? ─ no ─> unusable for that workload
      │ yes
      ▼
 performance evidence available?
   │ yes          │ no
   ▼              ▼
 cite it        show unknown
   │              │
   └──────┬───────┘
          ▼
  catalog/buying evidence
```

INT4 TOPS, INT8 TOPS, FP16 TFLOPS and custom dataflow throughput cannot be directly compared without the same model, quantization, context and runtime.

## Optional accelerator benchmark rules

For every accelerator benchmark, record at least:

- exact board/module and accelerator chip;
- host CPU and host RAM;
- attachment type and PCIe/link width;
- firmware and driver versions;
- compiler/runtime version;
- model and exact model hash;
- model conversion/quantization process;
- context size;
- prefill and decode throughput separately;
- accelerator-only power when available;
- **complete-node input power**;
- thermals and throttling;
- setup/reproducibility problems.

When comparable measured results exist, use them as an additional evidence dimension. The catalog itself remains valid without them; never replace missing measurements with marketing arithmetic.
