# Hardware Catalog Specification

## Purpose

`data/parts.json` is the catalog manifest and points to category-sized JSON fragments under `data/catalog/`. Together they are the source of truth for purchasable hardware and market references. `PARTS.md` is generated from them.

Catalog schema **v3** adds first-class accelerator and lifecycle metadata and allows an unresolved price to be represented honestly as `null`. v0.4.1 extends the same schema compatibly with catalog-first memory/evidence fields; the manifest version stays v3 because existing fragment structure remains compatible. The manifest is described by `specs/hardware-catalog.schema.json`; category fragments are described by `specs/hardware-part.schema.json`.

## Candidate categories

The project currently recognizes:

- `compute_node`
- `mini_pc`
- `dev_board`
- `sbc`
- `embedded_board`
- `specialty_board`
- `control_plane`
- `npu_accelerator`
- `tpu_accelerator`
- `ai_asic_accelerator`
- `fpga_accelerator`
- `adaptive_soc`
- `decommissioned_accelerator`
- `network`
- `memory`
- `storage`

A new class is acceptable when it advances the project charter and does not duplicate an existing category without a clear reason.

## Required common fields

Every part keeps:

- `id`
- `category`
- `name`
- `vendor`
- `price_min_usd`
- `price_max_usd`
- `price_status`
- `moq`
- `url`
- `verified_on`
- `listing_status`
- `plain_language`

Prices may be `null` only when both minimum and maximum are unresolved and `price_status` clearly explains why, such as `secondary_market_watch` or `board_price_not_resolved`. **Never use zero as a fake unknown price.**

## LLM candidate fields

LLM candidates additionally carry:

- `hardware_class`
- `llm_candidate`
- processor/architecture fields where known
- `memory_type`, `memory_capacity_gb`, `max_memory_gb` and `memory_config_status` where known
- memory bandwidth when a trustworthy value is available
- storage/network/expandability when applicable
- `power_target_w` or a clearly labelled power range when known
- `software_maturity`
- `risk_level`
- source notes separating manufacturer/seller/community evidence

## Accelerator fields

Every NPU, TPU, AI ASIC, FPGA/adaptive platform or decommissioned accelerator should additionally record:

- `accelerator_family`
- `accelerator`
- `host_mode`
- `host_requirements` when host-attached
- `precision_formats`
- `software_stack`
- `llm_support`
- `workload_role`
- `lifecycle_status`
- `power_scope` when a power number is present
- `peak_int4_tops`, `peak_int8_tops`, `peak_fp16_tflops` only when sourced

`llm_support` is more important than a TOPS number. Examples include `vendor_supported`, `research_only`, `not_supported_general_llm`, and `unproven_for_project`.

## Power scope rule

Never compare accelerator chip power with complete-node wall power without labelling the scope. Examples:

- `accelerator_chip_typical`
- `accelerator_board_tdp`
- `four_chip_module_typical_and_tdp_reference`
- `K26_SOM_typical_and_max`
- measured `complete_node_input`

Only measured complete-node power belongs in final system efficiency rankings.

## Price rules

A range on a multi-variant page is not the price of a specific SKU. Secondary-market pricing should be recent and explicitly marked. Manufacturer MSRP and vendor-store price are different evidence classes and should keep distinct `price_status` values.

## Inclusion test

Before adding hardware, answer in one sentence: **what hypothesis does this platform let us test?**

Examples:

- unusually high memory bandwidth per dollar;
- sub-15W 32GB node;
- dedicated 8GB GenAI NPU at a few watts;
- low-cost TPU with a maintained LLM compiler;
- scalable AI ASIC with high-speed chip interconnect;
- FPGA platform for custom ternary/INT4 transformer datapaths;
- obsolete enterprise accelerator that may become compelling below a threshold used price;
- fixed-function accelerator that saves total cluster energy by offloading vision.

## Memory configuration rule

`memory_capacity_gb` means RAM actually included/fixed in that exact referenced product configuration. Barebones use `null` and may record a verified `max_memory_gb`. `cpu_max_memory_gb` remains processor-theoretical metadata and must never be presented as included or board-verified memory.

## Performance evidence rule

Catalog inclusion does not require owning or benchmarking the product. When throughput evidence exists, optionally attach `performance_evidence` with source type, confidence, URL and notes as defined in `specs/EVIDENCE.md`. Unknown performance is valid. Do not fill the gap with fake tokens/sec.
