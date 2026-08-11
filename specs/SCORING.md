# Catalog Scoring Specification

## Purpose

`llm-cluster rank` is a **shopping/research shortlist**, not a simulated benchmark. Its job is to surface products worth investigating or buying.

The score may use:

- current acquisition price;
- included/fixed memory or discounted configurable memory potential;
- published power hints, clearly distinguished from complete-node measurements;
- software maturity;
- lifecycle/availability;
- setup/ownership risk.

The score must not use TOPS, TFLOPS or invented tokens/sec.

## Memory confidence

Memory contributes according to evidence quality:

1. included/fixed RAM — strongest;
2. verified board maximum — useful but requires additional purchase;
3. CPU theoretical maximum — weak and heavily discounted;
4. unknown — little/no capacity credit.

This prevents a barebone with a CPU that theoretically supports 256GB from appearing to include 256GB.

## Performance evidence is separate

When vendor/community/local performance exists, display it alongside source type and confidence. Do not multiply a weak benchmark into the catalog score. Product discovery and performance evidence are separate dimensions.

## Optional measured comparisons

The benchmark subsystem can compare genuinely compatible results (same model/workload dimensions) using measured tokens/sec, complete-node energy and acquisition cost. Those results are evidence records, not prerequisites for catalog inclusion.
