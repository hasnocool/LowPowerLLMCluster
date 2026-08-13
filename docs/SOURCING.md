# Sourcing & Seller Checklist

Marketplace listings often combine several CPU, RAM and SSD variants under one headline price. Treat every observed price as a **lead to verify**, not a guaranteed quote.

## Automated discovery workflow

v0.5 adds a discovery layer before canonical catalog curation:

```text
source adapter
    │
    ▼
raw ProductObservation
    │
    ├──> SQLite observation/history
    │       price/title/currency/stock
    │       disappearance/reappearance
    │
    ▼
normalization + confidence
    │
    ├── seller/source confidence
    ├── exact-SKU confidence
    ├── form factor / dimensions
    ├── DC / PSU / cooling / host needs
    └── board-memory evidence
    │
    ▼
review/promotion into data/catalog/*.json
```

Discovery output is **not automatically authoritative**. Promote an observation only when the exact purchasable configuration and evidence are strong enough to survive a catalog review.

Built-in adapters:

- `json`: maps structured vendor/reseller feeds through explicit field paths.
- `jsonld`: extracts schema.org `Product` records from current product pages.

Network requests are bounded and blocking `urllib` calls are executed outside the event loop. SQLite work also runs outside the event loop with a fresh connection per worker thread; no SQLite connection is shared between threads.

Use `config/discovery.example.json` as the starting contract. Do not commit private API credentials to the repository.

## Exact SKU promotion checklist

Before ordering or promoting a compute node, verify:

- exact CPU model and whether it is soldered to the board;
- manufacturer model/MPN/SKU, not just a marketplace listing-family title;
- exact price for the desired RAM/SSD or barebone configuration;
- number of SO-DIMM slots and **board-tested maximum RAM capacity**;
- source URL and verification date for the board RAM maximum;
- supported JEDEC DDR5 speed and whether 24GB/48GB modules work;
- number and PCIe generation of M.2 slots;
- Ethernet controller model and whether ports are 1/2.5/10GbE;
- whether OCuLink is PCIe x4 and which generation;
- BIOS access to power/TDP controls;
- Linux compatibility and known NIC/Wi-Fi chipset models;
- physical dimensions and form factor;
- DC input voltage/range/connector;
- included cooler, fan, heatsink and power adapter;
- host requirements for PCIe/M.2/USB accelerators;
- idle and sustained-load wall power if the seller has measurements;
- warranty, DOA handling and return process;
- whether the photographed PCB is the same revision that will ship.

For RAM and SSDs, verify the actual DRAM/NAND manufacturer and run memory/storage tests before trusting a node with long-running workloads.

## Confidence fields

Confidence values are 0-1 evidence weights, not guarantees:

- `source_confidence`: trust in the source class/identity.
- `seller_confidence`: source trust plus verified-seller/rating/review evidence when available.
- `sku_confidence`: strength of exact manufacturer/SKU/MPN/configuration identity.

A high seller score does not prove the SKU. A high SKU score does not prove the seller or the performance claim.

## Historical listing state

A single missing refresh is not automatically a delisting. `disappearance_after_runs` controls how many consecutive source refreshes must miss an item before a `disappeared` event is emitted. A later observation emits `reappeared`.

Persist history locally under `results/`; do not commit growing SQLite databases as catalog source-of-truth data.
