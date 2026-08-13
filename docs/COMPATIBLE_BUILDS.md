# Compatible Complete Builds

The live BOM layer now resolves **cross-component compatibility** before a sourced product can participate in a cheapest-complete-build recommendation.

## Why this exists

Selecting the cheapest CPU, motherboard, RAM, PSU and chassis independently can create a build that cannot physically or electrically work. The compatibility solver therefore evaluates combinations rather than individual line items.

The first supported constraints are:

- CPU socket ↔ motherboard socket;
- CPU memory support ↔ motherboard memory generation ↔ RAM generation;
- motherboard physical PCIe x16 slot and available GPU lanes;
- NVMe/M.2 storage support when the selected drive requires it;
- GPU recommended system PSU wattage ↔ selected PSU wattage;
- GPU power connectors when exact connector evidence is available;
- motherboard form factor ↔ chassis motherboard support;
- exact GPU length ↔ chassis GPU clearance when both are known;
- GPU slot width ↔ chassis slot capacity when both are known;
- CPU socket ↔ cooler mounting support;
- CPU cooler height ↔ chassis cooler clearance.

## Evidence rule

Unknown compatibility facts are never silently converted to `true`.

A combination is classified as:

- `compatible` — every required known constraint passes and no required fact is unresolved;
- `provisionally_compatible` — no contradiction is known, but one or more material facts are still unresolved;
- `incompatible` — at least one explicit constraint fails.

Board-partner GPU dimensions are a common reason for provisional status. A reference GPU family can have different cooler length/slot width across partner SKUs, so the exact listing must supply or be linked to exact physical dimensions before clearance is considered proven.

## Normalized compatibility facts

`data/market/bom-sourcing.json` defines product-family variants and facts that may be attached only when a listing matches the configured family terms. Initial host families include:

- Ryzen 5 5600 / AM4 / DDR4;
- B550 / AM4 / DDR4;
- Core i5-12400 / LGA1700 / DDR4 or DDR5 CPU support;
- B660 DDR4 / LGA1700;
- 32GB DDR4 DIMM kits;
- 1TB NVMe M.2 storage;
- 750W ATX PSUs;
- universal AM4/LGA1700 CPU coolers;
- ATX/mATX mid-tower chassis profiles.

The configuration is intentionally explicit and expandable rather than attempting to infer sockets or standards from unrelated product numbers.

## Cheapest compatible build generation

After live BOM sourcing finishes, `refresh_bom_market()` runs the constraint solver for every tracked `gpu_accelerator` catalog entry.

It combines the top live candidates for:

```text
CPU/host
motherboard
RAM
storage
PSU
cooling
chassis
```

and rejects incompatible combinations. When a sufficiently recent GPU market observation exists, its landed CAD cost is added to the host BOM and the solver records `complete_build_acquisition_cad`.

Results are persisted in:

`data/market/compatible-builds.json`

Use:

```bash
llm-cluster-refresh refresh-bom
llm-cluster-refresh compatible-builds
```

The second command shows the cheapest known build per tracked GPU and lists unresolved compatibility facts.

## Ranking

Fully compatible builds rank ahead of provisional builds. Inside a compatibility class, lower landed cost ranks first. Provisional builds receive a small penalty per unresolved fact so an apparently cheap but poorly documented combination does not automatically outrank a slightly more expensive well-evidenced build.

## Current limitations

The first implementation focuses on compatibility relationships that can be represented safely with structured catalog/config facts and conservative title extraction. It does not yet claim exact compatibility for every marketplace listing.

Highest-value follow-up evidence includes:

- exact board-partner GPU model dimensions and connectors;
- exact motherboard slot layout and lane sharing;
- BIOS version requirements for specific CPUs;
- exact PSU connector counts, not merely connector type presence;
- chassis radiator/fan conflicts that reduce GPU clearance;
- cooler RAM-height interference;
- OCuLink adapter host-lane topology.

Until those facts are sourced, the result remains provisional rather than fabricated.
