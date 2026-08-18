# Secondary-market accelerator intelligence

This workflow watches used and decommissioned datacenter accelerators for local-LLM value without treating a low listing price as proof that a card is useful.

## Promotion rule

A watched accelerator must pass **all existing canonical identity/source/stock gates** plus the accelerator-specific gates below:

1. the exact listing must match a configured accelerator family;
2. landed acquisition cost must be resolvable in CAD;
3. landed CAD must be at or below the watch ceiling;
4. transformer runtime evidence must be explicitly verified for the exact accelerator family;
5. the named runtime must belong to an approved runtime family for that watch;
6. when listing/spec evidence states memory capacity, it must agree with the watched identity.

Missing evidence fails closed. A cheap accelerator with no usable transformer stack stays Held. A supported accelerator whose landed price is above policy also stays Held.

## Initial watches

| Watch | Memory | Landed-CAD ceiling | Approved runtime families |
|---|---:|---:|---|
| AMD Alveo U200 | 64GB | CA$500 | Vitis / XRT plus separately verified transformer implementation |
| AMD Alveo U250 | 64GB | CA$600 | Vitis / XRT plus separately verified transformer implementation |
| AMD Alveo U55C | 16GB HBM2 | CA$650 | Vitis / XRT plus separately verified transformer implementation |
| Tenstorrent Wormhole n150 | 12GB GDDR6 | CA$650 | tt-inference-server / TT-Metalium / TT-NN / vLLM |
| Tenstorrent Wormhole n300 | 24GB GDDR6 | CA$950 | tt-inference-server / TT-Metalium / TT-NN / vLLM |
| Intel / Habana Gaudi | 32GB HBM2 | CA$700 | Optimum-Habana / SynapseAI / Gaudi software |
| Intel Gaudi2 | 96GB HBM2e | CA$1,800 | Optimum-Habana / SynapseAI / Gaudi software / vLLM |
| AMD Instinct MI60 | 32GB HBM2 | CA$450 | ROCm / llama.cpp / vLLM |
| NVIDIA A40 | 48GB GDDR6 | CA$1,400 | CUDA / llama.cpp / vLLM / TensorRT-LLM |

These ceilings are **editable policy values**, not fair-market-value estimates or buying recommendations. Their job is to identify listings cheap enough to justify deeper validation.

## Landed-CAD evidence

The gate prefers an explicitly preserved `landed_cost_cad` / `landed_cad` value when the market pipeline already computed one.

If no explicit value exists, it can calculate a planning value from:

- listing item price;
- listing shipping price;
- the repository's sourced CAD FX snapshot;
- the policy tax assumption (currently 12%).

This fallback does not invent customs duty, brokerage, or undocumented fees. If those materially apply, the explicit landed-cost evidence path should carry them and takes precedence.

## Runtime evidence boundary

A runtime name appearing in listing text is not enough. Promotion requires structured evidence with:

- `transformer_runtime_verified: true`; and
- a named `demonstrated_transformer_runtime`, `transformer_runtime`, or `llm_runtime`.

The name is then checked against the watch's approved runtime family aliases.

This deliberately distinguishes accelerator SDK availability from transformer usability. For example, AMD currently publishes XRT/Vitis support for Alveo cards such as U55C, but that alone does not make U55C a plug-and-play LLM accelerator. It remains Held until a reproducible transformer runtime is verified for that hardware. Intel Gaudi software, by contrast, has an explicit transformer/LLM software path including Optimum-Habana and current Llama inference support.

Primary references used when defining the initial runtime boundaries include:

- Intel Gaudi software: https://docs.habana.ai/
- Intel Gaudi model/runtime ecosystem: https://huggingface.co/docs/optimum/habana/index
- AMD Alveo support/downloads: https://www.amd.com/en/support/downloads/alveo-downloads.html
- AMD U55C product family: https://www.amd.com/en/products/accelerators/alveo/u55c.html
- Tenstorrent inference server: https://github.com/tenstorrent/tt-inference-server

## Autonomous scanning

`secondary-accelerator-scan` searches the focused families through eBay and manufacturer sources. The GitHub Actions market workflow runs the profile four times per day at the following **UTC** cron schedule:

```text
23 4,10,16,22 * * *
```

The profile is intentionally bounded:

- eBay: up to 18 queries/run, 72/day;
- manufacturer: up to 9 queries/run, 36/day.

Those daily budgets are sufficient for four maximum-budget runs without borrowing capacity from the broader daily/weekly discovery profiles.

## Audit trail

For a matched accelerator, promotion reports and canonical provenance include a `secondary_accelerator_policy` object with:

- watch ID and canonical category;
- observed landed CAD;
- configured landed-CAD ceiling;
- economic eligibility;
- runtime verification state and runtime name;
- final accelerator-policy eligibility.

Held decisions expose explicit reasons such as:

- `accelerator_landed_cost_missing`;
- `accelerator_landed_cost_above_threshold`;
- `accelerator_transformer_runtime_unverified`;
- `accelerator_runtime_not_in_approved_family`;
- `accelerator_memory_identity_mismatch`.

This keeps the automation conservative: discovery can be aggressive, but automatic canonical promotion remains evidence-driven.
