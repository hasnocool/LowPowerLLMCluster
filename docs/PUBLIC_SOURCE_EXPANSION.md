# Expanded public hardware discovery

LowPowerLLMCluster uses credential-free public web sources as a broad discovery layer for low-power LLM hardware. These sources complement authenticated marketplace APIs; they do not replace manufacturer evidence or the canonical catalog verification boundary.

## Source classes

### Hardware announcement sources

Announcement sources are early-warning inputs for newly announced SBCs, COMs, edge-AI modules, accelerators, mini PCs and embedded systems. They use `announcement_index` and are stored with `attributes.discovery_kind = "announcement"`.

Active announcement sources:

- LinuxGizmos
- CNX Software
- Hackster News
- ServeTheHome
- Phoronix News

These sources are intentionally lower-trust than manufacturers and capped at 20-24 article pages per cycle. An announcement can create a live discovery record, but it does not become authoritative price/spec evidence and is not silently promoted into the canonical catalog.

### SBC and embedded manufacturers

The default pool includes public catalogs from:

- Radxa
- PINE64
- Hardkernel / ODROID
- Seeed Studio
- DFRobot
- FriendlyElec
- Khadas
- Orange Pi
- UP Board
- Banana Pi
- Raspberry Pi

These sources are valuable for unusual ARM, RISC-V and x86 boards, high-memory SBCs, compact clusters, M.2 accelerators and systems with explicit DC-power specifications.

### Mini-PC, industrial and Linux system manufacturers

The pool also includes:

- Minisforum
- GMKtec
- Framework Marketplace
- ASRock Industrial
- System76
- Shuttle XPC
- HP Canada
- Dell Canada
- Lenovo Canada

### AI accelerator and edge-compute manufacturers

The public pool includes:

- NVIDIA Jetson
- Google Coral
- Hailo
- Tenstorrent

Manufacturer sources receive higher trust because they are stronger identity/specification evidence. Product pages that do not expose schema.org Product JSON-LD can fall back to public page metadata while preserving `metadata_fallback = true` so downstream logic knows the record is less structured.

### Retail discovery

Retail breadth continues to come from bounded public category pages at:

- Memory Express
- Canada Computers
- Best Buy Canada
- Newegg Canada

These are useful for current price/availability observations and exact retail SKU discovery.

## Runtime behavior

Every public source is bounded independently with:

- HTTPS-only seeds;
- same-host candidate restrictions;
- URL allow/deny patterns;
- `max_index_pages`;
- `max_candidate_pages`;
- bounded `subworkers`;
- shared HTTP retry/backoff and adaptive concurrency;
- circuit breaking;
- conditional response caching where applicable.

The current default configuration contains more than 30 credential-free public source groups. Continuous operation therefore gains broad coverage without turning any individual cycle into an unbounded web crawl.

## Announcement provenance

Announcement pages often contain `Article`/OpenGraph metadata instead of schema.org `Product`. `announcement_index` handles this explicitly:

1. discover bounded article URLs from a public index;
2. try normal Product JSON-LD parsing first;
3. if no Product exists, parse title, description and publication time from public page metadata;
4. save the record with `discovery_kind=announcement` and `metadata_fallback=true`;
5. allow later manufacturer/product association to enrich the discovery with authoritative model, SKU, price, memory, TOPS, power and availability facts.

This prevents useful early hardware announcements from disappearing while preserving the distinction between news and product evidence.

## Extending the registry

Good future additions include public product catalogs from more industrial PC vendors, Jetson carrier-board vendors, FPGA/AI accelerator manufacturers, refurbished OEM outlets, regional electronics distributors, open-hardware vendors, and vendor release feeds.

Before enabling a source by default, prefer stable public pages with clear provenance, HTTPS, conservative crawl limits and no login/API-key requirement. Do not add private endpoints, anti-bot bypasses, or sources whose terms prohibit automated access.
