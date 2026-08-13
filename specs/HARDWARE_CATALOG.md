# Hardware Catalog Specification

## Purpose

`data/parts.json` is the catalog manifest and points to category-sized JSON fragments under `data/catalog/`. Together they are the source of truth for reviewed hardware and market references. `PARTS.md` is generated from them.

Catalog schema **v3** remains structurally compatible while v0.5 adds discovery/evidence metadata. Newly discovered observations may live in `results/` or `data/discovery/` until an exact SKU is reviewed and promoted.

## Candidate categories

The project currently recognizes `compute_node`, `mini_pc`, `dev_board`, `sbc`, `embedded_board`, `specialty_board`, `control_plane`, `npu_accelerator`, `tpu_accelerator`, `ai_asic_accelerator`, `fpga_accelerator`, `adaptive_soc`, `decommissioned_accelerator`, `network`, `memory`, and `storage`.

## Required common fields

Every canonical part keeps:

- `id`, `category`, `name`, `vendor`;
- `price_min_usd`, `price_max_usd`, `price_status`;
- `moq`, `url`, `verified_on`, `listing_status`;
- `plain_language`.

Prices may be `null` only when both minimum and maximum are unresolved and `price_status` clearly explains why. **Never use zero as a fake unknown price.**

## Discovery / configuration confidence

When available, canonical records may carry:

- `source_confidence` (0-1);
- `seller_confidence` (0-1);
- `sku_confidence` (0-1);
- `form_factor`;
- `dimensions_mm` (`width_mm`, `depth_mm`, `height_mm`);
- `dc_input_v`, `dc_input_min_v`, `dc_input_max_v`, `dc_connector`;
- `psu_requirements`;
- `cooling_requirements`;
- `host_requirements`.

These fields improve shopping/configuration reliability; they do not prove inference performance.

## LLM candidate fields

LLM candidates additionally carry `hardware_class`, `llm_candidate`, processor/architecture fields where known, memory metadata, storage/network/expandability when applicable, power hints with scope, `software_maturity`, `risk_level`, and source notes.

## Memory configuration rule

`memory_capacity_gb` means RAM actually included/fixed in that exact referenced product configuration. Barebones use `null` and may record a verified `max_memory_gb`.

Where possible, board maximum evidence should also carry:

- `max_memory_source_url`;
- `max_memory_verified_on`.

`cpu_max_memory_gb` remains processor-theoretical metadata and must never be presented as included or board-verified memory.

## Accelerator fields

Every NPU, TPU, AI ASIC, FPGA/adaptive platform or decommissioned accelerator should additionally record accelerator family/name, host mode/requirements, precision formats, software stack, LLM support, workload role, lifecycle status and power scope when power is present.

`llm_support` is more important than a TOPS number. A fixed-function accelerator can stay in the catalog as a specialist without being an LLM candidate.

## Power scope rule

Never compare accelerator chip power, accelerator-board power or processor TDP/cTDP with complete-node wall power without labelling the scope.

Only measured complete-node input power belongs in final system efficiency rankings.

## Price rules

A range on a multi-variant page is not the price of a specific SKU. Secondary-market pricing should be recent and explicitly marked. Manufacturer MSRP, official-store price and marketplace price are different evidence classes.

Canada landed-cost calculations are derived planning outputs, not canonical product price fields. They must preserve FX snapshot/date, shipping, duty, brokerage and tax assumptions.

## Performance evidence rule

Catalog inclusion does not require owning or benchmarking the product. When throughput evidence exists, attach provenance or keep normalized records under `data/performance/` as defined in `specs/EVIDENCE.md`.

Unknown performance is valid. Do not fill the gap with fake tokens/sec.
