# Evidence & Estimation Specification

The project is a **catalog first**. Performance evidence is optional metadata attached to a product; owning the hardware is not required to catalog it.

## Performance provenance

Use one of these source types:

- `measured_local` — measured by this project on hardware physically available to the contributor.
- `community_measured` — reproducible third-party/community benchmark with identifiable hardware/runtime/model.
- `vendor_measured` — vendor-published workload benchmark with enough detail to understand what was measured.
- `derived_estimate` — mathematical transformation of measured evidence; preserve the source measurements.
- `spec_based_estimate` — weak estimate based primarily on specifications; never present as a benchmark.
- `unknown` — no useful throughput evidence yet.

Confidence is separately `high`, `medium`, `low`, or `unknown`. Source type and confidence are not interchangeable.

## Sourced performance-record contract

Normalized records under `data/performance/` or imported from third parties preserve at least:

- hardware ID;
- source type, source URL and independent source identity;
- model;
- runtime and runtime version when known;
- workload class;
- metric/value/unit;
- quantization;
- context length when relevant;
- power value and power scope when supplied;
- observation/publication date.

See `specs/performance-record.schema.json`.

## Confidence-aware ranges

A throughput range may be calculated only when **at least two independent measured sources** are compatible on the complete comparison signature:

```text
hardware + model + runtime + workload + metric + unit + quantization + context
```

`measured_local`, `community_measured`, and `vendor_measured` are eligible. `derived_estimate`, `spec_based_estimate`, and `unknown` do not create a measured range.

Mirrored/reposted copies must eventually be deduplicated before being counted as independent sources. Until enough compatible independent records exist, show the individual sourced evidence or `unknown` rather than manufacturing a range.

Specialist `vision`, `audio`, `embedding`, `reranking`, and other specialist records must remain separate from `llm_prefill` / `llm_decode` throughput.

## Safe derived estimates

The catalog may derive **capacity screens** from model parameter count, nominal bits/weight and known memory. These estimates must say what they do not know: runtime overhead, KV cache, context architecture, backend allocation and reserved system memory.

Model-family presets are convenience inputs to that same capacity formula; they do not create performance evidence.

The catalog must **not** generate tokens/sec from TOPS, TFLOPS, core count, memory bandwidth, TDP or another device's benchmark alone. If no sourced throughput exists, show `unknown`.

## Memory semantics

- `memory_capacity_gb`: memory actually included/fixed in the referenced configuration.
- `max_memory_gb`: verified maximum for the actual board/product, when known.
- `max_memory_source_url`: source supporting that board/product maximum when available.
- `max_memory_verified_on`: date that board-level evidence was checked.
- `cpu_max_memory_gb`: processor-theoretical maximum only; this does not prove the board BIOS/slots support it.
- `memory_config_status`: `included`, `fixed`, `configurable`, or `unknown`.

A barebone must never look like it includes the CPU's theoretical maximum RAM.

## Power boundaries

Every power value needs a scope. Processor `default_tdp_w` / cTDP values are processor boundaries, **not complete-node watts**. Accelerator chip or board power is also not host+accelerator wall power.

Complete-system efficiency comparisons require a measured complete-node scope such as `complete_node_input`.

## Benchmark subsystem

The benchmark harness remains useful for local or contributed measurements, but it is optional evidence tooling. It must not become a prerequisite for adding or ranking catalog products.
