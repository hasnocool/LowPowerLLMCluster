# Sourcing & Seller Checklist

Alibaba listings often combine several CPU, RAM and SSD variants under one headline price. Treat every price in this repository as a **lead to verify**, not a guaranteed quote.

Before ordering a compute node, ask the seller to confirm in writing:

- exact CPU model and whether it is soldered to the board;
- exact price for the desired RAM/SSD or barebone configuration;
- number of SO-DIMM slots and tested maximum RAM capacity;
- supported JEDEC DDR5 speed and whether 24GB/48GB modules work;
- number and PCIe generation of M.2 slots;
- Ethernet controller model and whether ports are 1/2.5/10GbE;
- whether OCuLink is PCIe x4 and which generation;
- BIOS access to power/TDP controls;
- Linux compatibility and known NIC/Wi-Fi chipset models;
- included cooler, fan, heatsink and power adapter;
- idle and sustained-load wall power if the seller has measurements;
- warranty, DOA handling and return process;
- whether the photographed PCB is the same revision that will ship.

For RAM and SSDs, verify the actual DRAM/NAND manufacturer and run memory/storage tests before trusting a node with long-running workloads.
