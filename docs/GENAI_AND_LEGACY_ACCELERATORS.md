# Current GenAI and legacy large-memory accelerators

This expansion separates two very different hardware opportunities:

1. **current purpose-built AI accelerators with a demonstrated transformer runtime**, and
2. **large-memory legacy/secondary-market accelerators that remain programmable but require custom work before they should be treated as LLM hardware**.

The project does not promote a device merely because a vendor advertises TOPS.

## Current demonstrated-transformer accelerators

| Accelerator | Local memory | Board power scope | Demonstrated runtime | Evidence boundary |
|---|---:|---:|---|---|
| FuriosaAI RNGD | 48GB HBM3 | 180W accelerator TDP | Furiosa-LLM / OpenAI-compatible server | Production LLM software exists; no public single-card acquisition price is asserted. |
| Tenstorrent Blackhole p150 | 32GB GDDR6 | 300W accelerator TBP | tt-inference-server / vLLM integration | Tenstorrent publishes active Llama/Falcon model support; board power is not host wall power. |
| Tenstorrent Wormhole n300s | 24GB GDDR6 | 300W accelerator TBP | tt-inference-server / vLLM integration | Current previous-generation product with active software; multi-device model support must not be attributed to one card. |

### FuriosaAI RNGD

FuriosaAI documents RNGD as a PCIe Gen5 x16 inference accelerator with 48GB HBM3 and 1.5TB/s memory bandwidth. Current 2026 Furiosa documentation provides a dedicated `Furiosa-LLM` stack, OpenAI-compatible serving, supported-model documentation and production deployment guidance.

Primary evidence:

- https://furiosa.ai/renegade-spec
- https://developer.furiosa.ai/latest/en/overview/rngd.html
- https://developer.furiosa.ai/v2026.2.0/en/index.html

The catalog records the current 180W board TDP. That is **accelerator-board power**, not complete server input power.

### Tenstorrent Blackhole p150

Tenstorrent documents current Blackhole p150 cards with 32GB GDDR6, 512GB/s memory bandwidth, PCIe Gen5 x16 and 300W board power. Tenstorrent's actively released `tt-inference-server` stack includes model-specific support and CI/release artifacts for transformer inference including Llama and Falcon families.

Primary evidence:

- https://docs.tenstorrent.com/aibs/blackhole/index.html
- https://tenstorrent.com/en/hardware/cards
- https://github.com/tenstorrent/tt-inference-server/releases

The catalog does not infer tokens/sec from BLOCKFP8 compute specifications.

### Tenstorrent Wormhole n300s

The n300s contains two Wormhole ASICs and 24GB GDDR6 at 576GB/s. Tenstorrent continues to sell and support the Wormhole card family, and its inference-server/model releases explicitly include Wormhole hardware.

Primary evidence:

- https://docs.tenstorrent.com/aibs/wormhole/specifications.html
- https://tenstorrent.com/en/hardware/cards
- https://github.com/tenstorrent/tt-inference-server/releases

Models demonstrated on multi-card Wormhole systems remain labeled as **multi-device** evidence and are not treated as single-card capacity/performance claims.

## Large-memory secondary-market FPGA watches

| Accelerator | Card memory | Toolchain state | LLM status |
|---|---:|---|---|
| AMD Alveo U250 | 64GB DDR4 ECC | Current-user XRT/Vitis packages still published | Research only; custom transformer implementation/port required |
| AMD Alveo U200 | 64GB DDR4 ECC | Current-user XRT/Vitis packages still published | Research only; custom transformer implementation/port required |

AMD documents both U200 and U250 with 64GB DDR4 and 77GB/s aggregate external-memory bandwidth. AMD currently states that these cards remain supported for existing users while recommending newer Alveo V80 hardware for new designs. Current XRT/deployment packages are still published, including Ubuntu 24.04 support pages.

Primary evidence:

- https://www.amd.com/en/products/accelerators/alveo/u250/a-u250-a64g-pq-g.html
- https://www.amd.com/en/products/accelerators/alveo/u200/a-u200-a64g-pq-g.html
- https://www.amd.com/en/support/downloads/alveo-downloads.html/accelerators/alveo/u250.html
- https://www.amd.com/en/support/downloads/alveo-downloads.html/accelerators/alveo/u200.html
- https://docs.amd.com/r/en-US/ds962-u200-u250/Alveo-Product-Details

These cards are attractive **only if secondary-market landed cost becomes low enough to justify FPGA development effort**. Their 64GB memory capacity must not be compared directly with a 64GB GPU: DDR bandwidth, programming model, model kernels, quantization flow and deployment effort are fundamentally different.

## Promotion rules

A current NPU/ASIC/TPU may be an `llm_candidate=true` entry only when all of the following are true:

- exact hardware identity is known;
- local memory capacity is sourced;
- a vendor/project-maintained transformer or LLM runtime is named;
- at least one transformer/LLM model family is demonstrated on the relevant hardware family;
- board/chip power is labeled with its measurement boundary;
- TOPS/TFLOPS are not converted into tokens/sec.

A legacy FPGA/accelerator with large memory remains `llm_candidate=false` when it has only a general programmable toolchain and no project-approved transformer runtime.

## Remaining work

The next useful step is **live secondary-market pricing and exact runtime evidence**:

- track U200/U250/U55C and other decommissioning datacenter cards when landed-CAD prices fall enough to justify experimentation;
- ingest exact-card transformer implementations only when build instructions, model identity, precision and measured hardware provenance are reproducible;
- compare complete-host power and total acquisition cost rather than accelerator TDP or card sticker price alone;
- expand current NPU/ASIC coverage only when a real transformer runtime exists, not on TOPS marketing alone.
