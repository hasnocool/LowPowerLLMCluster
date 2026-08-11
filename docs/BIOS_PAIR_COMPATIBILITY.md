# CPU / Motherboard BIOS Pair Compatibility

CPU socket equality is necessary, but it is not sufficient to prove that a motherboard can boot a particular CPU. Firmware support can depend on a minimum BIOS revision, and some CPUs may be explicitly unsupported even when the socket matches.

## Data flow

```text
verified motherboard manufacturer page
        |
        v
structured HTML CPU / BIOS support table
        |
        v
retain every parsed support row on motherboard candidate
        |
        +-- cpu_model
        +-- minimum_bios_version
        +-- support_status
        +-- source/provenance
        |
        v
build solver pairs exact CPU + motherboard
        |
        v
pair-level BIOS evaluation
```

The matrix is retained under the motherboard candidate's structured enrichment metadata. It is not flattened into one global `minimum_bios_version`, because the correct BIOS depends on which CPU the solver actually pairs with the board.

## Pair states

`evaluate_cpu_bios_pair()` produces one of three states:

- `supported` — the selected CPU matches a manufacturer support-table row. The row's minimum BIOS revision is retained.
- `unsupported` — the matching row explicitly says unsupported, or the CPU is absent from a matrix that a future source can explicitly prove is complete.
- `unresolved` — no usable matrix exists, CPU identity is insufficient, or the CPU is absent from a matrix whose completeness cannot be proven.

Absence from a normal static HTML table is **not** treated as proof of incompatibility. Manufacturer pages may be paginated, rendered through JavaScript, filtered, or incomplete. `cpu_support_matrix_complete` therefore defaults to `false`.

## Minimum BIOS versus shipped BIOS

A support row such as:

```text
Ryzen 5 5600 -> minimum BIOS 7C56vA9
```

proves that the CPU/motherboard combination is supported at or above that firmware revision. It does **not** prove that a particular retail board currently has that BIOS installed.

The build may therefore remain hardware-compatible while carrying a warning such as:

```text
cpu_bios: selected CPU requires motherboard BIOS >= 7C56vA9; shipped BIOS version is unknown
```

A future layer can use listing/manufacturing revision evidence, BIOS Flashback capability, or seller-provided BIOS revision to estimate whether an update is likely to be required before first boot.

## Identity matching

CPU support rows are matched only after the build solver selects a CPU. Identity candidates are derived from stronger product identity first where available:

- normalized CPU model compatibility fact;
- manufacturer part number / MPN;
- listing SKU;
- exact live listing title.

Exact normalized matches outrank substring/model matches. Ambiguous absence does not become an unsupported result.

## Provenance

Each retained matrix row keeps:

- manufacturer source URL;
- source type (`manufacturer_support_table`);
- observation time;
- extraction method (`cpu_bios_support_matrix`);
- exact-SKU/manufacturer association ID;
- identity confidence;
- original support-table row position.

The pair result copies the matched row provenance into the generated compatible-build record.

## Solver behavior

The compatibility solver now treats BIOS support as a real cross-component constraint:

- explicit unsupported row -> reject build;
- supported row -> retain minimum BIOS and warning if one is specified;
- no support evidence -> provisional `cpu_bios_support` unknown;
- incomplete matrix with no matching row -> provisional, not rejected;
- explicitly complete matrix with no matching row -> reject.

This constraint is evaluated after CPU and motherboard selection, alongside socket, DDR generation, PCIe, storage, PSU, chassis, cooler and GPU requirements.

## Remaining work

Useful next refinements include:

- discover manufacturer CPU-support endpoints that are not linked directly from product pages;
- recognize paginated/API-backed support matrices and prove matrix completeness when possible;
- retain motherboard BIOS Flashback / CPU-less update capability;
- derive likely shipped BIOS from hardware revision or manufacture-date evidence where sources provide it;
- include BIOS-update friction in recommendation scoring without treating it as a performance estimate.
