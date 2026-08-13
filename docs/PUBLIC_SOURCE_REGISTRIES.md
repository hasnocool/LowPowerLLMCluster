# Public source registries

The discovery service can load large credential-free source pools from external JSON registries instead of placing every source in `discovery.example.json`.

## Default behavior

When the repository default `config/discovery.example.json` is used, the sibling `config/public_sources.extra.json` registry is loaded automatically. Custom configs remain isolated unless they explicitly declare `source_files`.

```json
{
  "source_files": ["my-public-sources.json"],
  "sources": []
}
```

Registry paths are resolved relative to the primary discovery config. A registry may be either a JSON object with a `sources` array or a raw array of source objects. Duplicate source names are rejected before the HTTP client begins discovery.

## Expanded public pool

`public_sources.extra.json` adds 40 bounded, credential-free source groups to the existing public discovery configuration. The combined default pool is intentionally broad enough to find hardware that does not normally appear in consumer GPU/desktop categories.

### Industrial and embedded edge systems

AAEON, SECO, congatec, Axiomtek, Lanner, Portwell, Kontron, Advantech, and Premio expose public product or solution catalogs covering fanless systems, COMs, SBCs, industrial PCs, Edge AI appliances, Jetson systems, GPU workstations, NPUs, and accelerator-capable boxes.

### NVIDIA Jetson ecosystem

Connect Tech, Forecr, Auvidea, Aetina, and Waveshare add public carrier-board, development-kit, and Jetson-compatible system catalogs. These sources are especially useful for discovering unusual power, I/O, camera, PCIe, and module combinations that are absent from mainstream retail indexes.

### FPGA and PCIe accelerators

AMD Alveo, Digilent, and BittWare add public accelerator-card and FPGA/SoC board discovery. This includes high-memory/HBM cards, low-power development boards, PCIe accelerators, and adaptable-compute hardware that can be relevant to specialized inference or preprocessing workloads.

### Refurbished enterprise systems

PC Server & Parts and Techbuyer add public refurbished workstation/server inventory. These sources can surface inexpensive high-memory towers, multi-GPU-capable workstations, older professional GPUs, and server platforms that may be useful when acquisition cost matters more than absolute efficiency.

### Public electronics distributors

Mouser Canada, DigiKey Canada, and Newark Canada expose large public catalogs with stock, pricing, manufacturer part numbers, RAM, power, form factor, processor, and other parametric data. These sources improve identity and availability coverage without requiring API credentials.

### Vendor release feeds

congatec and Kontron public release pages are included as bounded announcement sources. Announcement records remain lower-trust discovery evidence and are tagged separately from manufacturer product records until they can be associated with a product page or SKU.

## Bounds

Every extra public source remains independently constrained by:

- HTTPS seeds;
- same-host candidate filtering;
- explicit include/exclude patterns;
- `max_index_pages`;
- `max_candidate_pages`;
- low per-source `subworkers`;
- global and per-host HTTP limits;
- adaptive concurrency;
- retry/backoff and circuit breakers;
- conditional cache behavior.

The registry is intended to broaden discovery, not create an unrestricted crawler.

## Runtime visibility

Refresh output now includes:

```text
runtime.source_count
runtime.source_registry_files
```

These fields make it possible to confirm that an installed service actually loaded the expanded registry instead of silently running only the built-in source list.

## Adding another registry

Create another JSON file beside the main config and reference it with `source_files`. Keep names globally unique across the primary config and every registry. This makes future 30–50 source expansions data-only changes unless a new discovery method is required.
