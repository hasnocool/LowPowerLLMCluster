# Project Guardrails

These rules keep LowPowerLLMCluster useful as a catalog and prevent performance theater.

## 1. Catalog first

The primary deliverable is searchable product/spec/price/evidence data. Benchmark tooling is optional supporting infrastructure. A product does not need a local benchmark to belong in the catalog.

## 2. Evidence hierarchy and provenance

Keep manufacturer facts, seller facts, community observations, vendor/community benchmarks, derived estimates and project-local measurements distinct. Preserve URLs and verification dates.

## 3. Unknown is a valid answer

If throughput, exact board memory limit, power or pricing is unresolved, record it as unknown. Never manufacture a precise number merely to fill a table cell.

## 4. No fake tokens/sec

TOPS, TFLOPS, cores, clocks, bandwidth and TDP can explain *why a product is interesting*. They cannot be converted directly into claimed LLM throughput. Tokens/sec needs a real source or remains unknown.

## 5. Safe capacity estimation is allowed

Model parameter count × nominal bits/weight may be used as a transparent **weights-only/model-fit screen** with explicit runtime/KV-cache headroom caveats. This is capacity planning, not a performance benchmark.

## 6. Memory semantics must be honest

`memory_capacity_gb` means included/fixed memory in the referenced configuration. Barebones must not inherit the CPU theoretical maximum. Board maximum and CPU maximum are separate fields/evidence levels.

## 7. Whole-system ownership cost matters

Track required RAM, host computer, storage, PSU, cooling, adapters, networking and lifecycle risk. A cheap accelerator is not a cheap node if it requires an expensive host.

## 8. Power boundaries stay explicit

Chip power, accelerator-board TDP, CPU package power and complete-node input power are different. Published power is useful catalog metadata; measured complete-node power is required for canonical measured energy-efficiency claims.

## 9. Experimental hardware stays experimental

BC-250 modifications, custom FPGA datapaths and unsupported drivers stay clearly labelled. Interesting does not mean production-ready.

## 10. Specialist metrics stay specialist

Vision FPS, detections/s, embeddings/s and audio throughput are useful but are not tokens/sec. Compare within workload class.

## 11. Documentation and machine-readable data move together

Catalog fragments are authoritative. Generate `PARTS.md`; update README/TODO/CHANGELOG/specs when semantics change.

## 12. Automation must preserve last-known-good data

Future price/product discovery should be rate-limited, source-attributed and failure-safe. A scraper/API outage must not destroy known catalog state.
