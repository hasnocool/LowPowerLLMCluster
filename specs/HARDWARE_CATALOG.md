# Hardware Catalog Specification

## Purpose

`data/parts.json` is the source of truth for purchasable hardware and market references. `PARTS.md` is generated from it.

## Candidate classes

`mini_pc`, `mobile_cpu_board`, `embedded_board`, `sbc`, `edge_ai_developer_kit`, `salvaged_accelerated_apu_board`, `accelerator`, and `ultra_low_power_x86` are all valid directions. A new class is acceptable when it advances the project charter.

## Required common fields

Every part keeps: `id`, `category`, `name`, `vendor`, `price_min_usd`, `price_max_usd`, `moq`, `url`, `verified_on`, `listing_status`, and `plain_language`.

LLM candidates should additionally carry:

- `hardware_class`
- `llm_candidate`
- processor/architecture fields where known
- `memory_type` and `memory_capacity_gb`
- memory bandwidth when a trustworthy value is available
- storage/network/expandability
- `power_target_w` or a clearly labelled power range
- `software_maturity`
- `risk_level`
- `source_notes` distinguishing manufacturer/seller/community evidence

## Price rules

A range on a multi-variant page is not the price of a specific SKU. Use a status such as `verify_32gb_variant_price`. Secondary-market pricing should be a recent observed range and marked accordingly.

## Inclusion test

Before adding hardware, answer in one sentence: **what hypothesis does this platform let us test?** Examples: unusually high memory bandwidth per dollar, sub-15W 32GB node, cheap CUDA edge inference, dense standard-form-factor mobile CPU, or ultra-low-power control plane.
