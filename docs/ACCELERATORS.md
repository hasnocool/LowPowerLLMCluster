# Accelerator Landscape

LowPowerLLMCluster treats **GPUs, NPUs, TPUs, AI ASICs, FPGAs and adaptive SoCs as distinct accelerator families** with different software, memory and power tradeoffs. The useful question is not "how many TOPS?" It is:

> **Is this exact product worth tracking or buying for a real workload, given its memory, runtime, price, host requirements, power scope and evidence quality?**

Discrete GPUs are now a first-class sourcing category rather than an implicit baseline outside the catalog. See `docs/GPUS.md` for GPU-specific VRAM, board-partner, used-market and power rules.

## The expanded accelerator map

```text
                           AI ACCELERATOR DISCOVERY
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   GENERAL GPUs                GENAI / LLM               SPECIALIST / RESEARCH
        │                           │                           │
 NVIDIA CUDA                 Hailo-10H NPU               Coral Edge TPU
 AMD ROCm/Vulkan             SOPHGO BM1688               MemryX MX3
 Intel SYCL/Vulkan           BM1684X TPU                 AMD Kria / Versal
        │                    Tenstorrent ASIC             Alveo / EOL hardware
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                         WORKLOAD-AWARE BUYING / ROUTING
```

## Why this matters

A heterogeneous cluster can reduce average power by sending work to the smallest device that actually supports it, while the market layer can still discover a larger GPU when VRAM-per-dollar makes it the better purchase.

```text
       incoming task
            │
            ▼
   ┌──────────────────┐
   │ What workload is │
   │ this really?     │
   └────────┬─────────┘
            │
     ┌──────┼───────────────────┐
     │      │                   │
     ▼      ▼                   ▼
  vision   small LLM        larger LLM
     │      │                   │
     ▼      ▼                   ▼
 Coral /  Hailo /          discrete GPU /
 MemryX   SOPHGO           high-memory node
```

A 2W vision TPU that cannot run an LLM can still improve the **whole cluster** if it keeps a larger inference node asleep. Conversely, a 24GB used GPU may be a strong model-capacity bargain even though its board power makes it unsuitable for an always-on low-power role.

## Families

### Discrete GPU

Examples: NVIDIA GeForce RTX, AMD Radeon and Intel Arc.

GPUs combine relatively large fixed VRAM with mature or emerging general-purpose inference stacks. They are tracked as `gpu_accelerator` entries because their purchasing constraints differ materially from system nodes and fixed-function accelerators.

The catalog records:

- fixed VRAM and memory type;
- CUDA, ROCm/HIP/Vulkan or oneAPI/SYCL software path;
- exact host requirements;
- board TGP/TBP power scope;
- lifecycle/current-versus-used-market status;
- live seller/board-partner evidence separately from reference GPU identity.

GPU VRAM can feed the conservative model-fit screen. GPU TOPS/TFLOPS cannot be converted into tokens/sec, and board TGP/TBP cannot be presented as complete-node power.

### NPU

Examples: Hailo-10H and MemryX MX3.

NPUs are purpose-built neural processors. Their usefulness depends heavily on the compiler/runtime and model memory architecture. Hailo-10H is especially important because it adds dedicated memory and an explicit generative-AI path; MX3 is tracked mainly as a streaming-vision specialist.

### TPU

Examples: SOPHGO BM1684X/BM1688 and Google Coral Edge TPU.

"TPU" does not imply one common programming model. SOPHGO's current LLM-TPU stack makes BM1684X/BM1688 genuine transformer candidates. Coral remains a fixed INT8 TensorFlow Lite specialist and should not be ranked as a general LLM worker.

### AI ASIC

Example: Tenstorrent Wormhole.

Purpose-built AI ASICs can offer model-oriented memory/interconnect designs that commodity Ethernet clusters cannot reproduce. Wormhole is too power-hungry to be a normal low-power node, but its open software stack and high-speed accelerator links make it a valuable performance/scaling reference.

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

The same rule applies to GPUs: gaming benchmark rankings, CUDA core counts, shader counts, AI TOPS and FP16 TFLOPS are not direct LLM throughput measurements.

## Optional accelerator benchmark rules

For every accelerator benchmark, including GPUs, record at least:

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
- **complete-node input power** when efficiency is being compared;
- thermals and throttling;
- setup/reproducibility problems.

When comparable measured results exist, use them as an additional evidence dimension. The catalog itself remains valid without them; never replace missing measurements with marketing arithmetic.
