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

## Safe derived estimates

The catalog may derive **capacity screens** from model parameter count, nominal bits/weight and known memory. These estimates must say what they do not know: runtime overhead, KV cache, context architecture, backend allocation and reserved system memory.

The catalog must **not** generate tokens/sec from TOPS, TFLOPS, core count, memory bandwidth, TDP or another device's benchmark alone. If no sourced throughput exists, show `unknown`.

## Memory semantics

- `memory_capacity_gb`: memory actually included/fixed in the referenced configuration.
- `max_memory_gb`: verified maximum for the actual board/product, when known.
- `cpu_max_memory_gb`: processor-theoretical maximum only; this does not prove the board BIOS/slots support it.
- `memory_config_status`: `included`, `fixed`, `configurable`, or `unknown`.

A barebone must never look like it includes the CPU's theoretical maximum RAM.

## Benchmark subsystem

The v0.4 benchmark harness remains useful for local or contributed measurements, but it is optional evidence tooling. It must not become a prerequisite for adding or ranking catalog products.
