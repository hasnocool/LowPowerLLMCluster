# TODO

## Highest priority

- [ ] Define and implement machine-readable benchmark result schema.
- [ ] Benchmark x86 Ryzen, BC-250, Jetson Orin Nano and RK3588 with a shared llama.cpp workload matrix.
- [ ] Measure complete-node wall/DC power at idle, model-loaded idle, prefill and decode.
- [ ] Calculate measured tokens/joule and tokens/$ by model/quantization.
- [ ] Find more unusual high-memory-bandwidth-per-dollar hardware: decommissioned accelerators, console-derived boards, embedded APUs and workstation laptop boards.
- [ ] Verify exact 32GB Orange Pi 5 Plus SKU pricing rather than relying on family ranges.
- [ ] Track BC-250 stock vs modified configurations separately.

## Hardware discovery

- [ ] Add more Ryzen 7840HS/8845HS/8945HS bare motherboards.
- [ ] Compare Ryzen AI 300 mini PCs/mainboards with high-capacity DDR5.
- [ ] Evaluate Radxa ROCK 5 ITX+ availability and RK3588 Linux/Vulkan maturity.
- [ ] Evaluate Jetson Orin NX / AGX only where memory capacity justifies price.
- [ ] Add Intel Lunar Lake / low-power Core Ultra references where memory capacity is sufficient.
- [ ] Add used Apple Silicon nodes as efficiency references without assuming cluster sharding is practical.
- [ ] Add PCIe/OCuLink accelerator candidates and complete-node power cost.

## Sourcing

- [ ] Build asynchronous price-source adapters using permitted APIs/pages.
- [ ] Add historical prices and listing disappearance detection.
- [ ] Add CAD conversion and landed-cost estimates for Canada.
- [ ] Add physical dimensions, DC input voltage and connector type.
- [ ] Add supplier confidence and return-policy fields.

## Cluster software

- [ ] Node daemon.
- [ ] Discovery and health protocol.
- [ ] OpenAI-compatible router.
- [ ] Automatic model placement.
- [ ] Power-aware scheduling.
- [ ] llama.cpp RPC fallback.
- [ ] Separate always-on control plane from inference workers.
