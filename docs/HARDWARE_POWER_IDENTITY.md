# Hardware-specific power identity

Power evidence is matched at the narrowest identity supported by explicit facts. Missing fields remain unknown; identity enrichment must not guess silicon, board revisions, controller/NAND, memory topology, or host configuration.

## Narrow identity fields

The adaptive power layer can now distinguish:

- Apple machine identifier, A-number, part number, SoC, explicit GPU core count, RAM, SSD and screen size;
- mobile device model/SKU, SoC and SoC variant;
- SSD/NVMe controller, NAND type, capacity and interface;
- GPU board partner/MPN, PCB/board revision, VBIOS, host CPU, motherboard, PSU and host RAM;
- RAM capacity, module count, per-module capacity, channel count and memory type.

These dimensions are conflict constraints. If an observation says `Phison E18 + Micron 176L TLC`, it is not an exact match for the same retail SSD name with a different controller or NAND revision. Likewise, an RTX 3090 measurement on one host cannot be silently treated as exact complete-node evidence for a different CPU/motherboard/PSU configuration.

## Matching

The matcher selects only the highest-specificity compatible evidence distribution. Broader family/category samples remain available as fallback but do not get averaged together with a narrower exact-hardware distribution.

Direct per-part measurements still outrank all learned distributions. Power scope remains independent of identity specificity: a very exact internal-rail observation is still not eligible to represent wall input.
