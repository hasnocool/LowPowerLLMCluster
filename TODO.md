# TODO

## Highest priority — collect real v0.4 measurements

- [x] Implement the machine-readable benchmark result schema.
- [x] Build a common benchmark harness that invokes llama.cpp plus accelerator-native runtimes without pretending they share one backend.
- [x] Separate LLM prefill/decode metrics from specialist vision/audio/embedding metrics.
- [x] Enforce complete-node input power for canonical energy-efficiency metrics.
- [ ] Benchmark x86 Ryzen, BC-250, Jetson Orin Nano, RK3588, Hailo-10H, SOPHGO BM1688/BM1684X and at least one FPGA/adaptive platform with controlled workloads.
- [ ] Integrate at least one live external DC/wall power meter CLI with the asynchronous `command` probe.
- [ ] Add persistent-runtime adapters for model-loaded-idle and clean steady-state power windows.
- [ ] Measure complete-node input power at idle, model-loaded idle, prefill and decode on the first physical node set.
- [ ] Calculate and publish measured tokens/joule and throughput/$ by model/quantization/runtime.
- [ ] Measure whether specialist offload (Coral/MemryX-class vision) lowers whole-cluster energy versus waking a general LLM node.
- [ ] Add runtime-specific bridge scripts on real Hailo, SOPHGO, Tenstorrent and FPGA hardware.
- [ ] Add model conversion/compile time, artifact size and reproducibility metadata to vendor bridge results.

## Accelerator discovery

- [ ] Find direct-China and used-market Hailo-10H M.2 pricing independent of Raspberry Pi AI HAT+ 2.
- [ ] Find cheaper BM1684X/BM1688 boards and SoMs on Alibaba/AliExpress and verify 8GB/16GB exact SKUs.
- [ ] Compare Tenstorrent Wormhole n150s with newer Blackhole p100/p150 only where tokens/joule or memory capacity justifies 300W-class power.
- [ ] Search secondary markets for Alveo U50/U55C/V70 and establish price thresholds that justify FPGA/adaptive experiments.
- [ ] Evaluate AMD Versal AI Edge Gen 2 boards as affordable products become available.
- [ ] Add other current GenAI NPUs/ASICs only when a real transformer runtime exists.
- [ ] Track unusual/decommissioned accelerator families including legacy VPUs, edge inference cards and HBM FPGA cards.
- [ ] Keep fixed-function vision accelerators separate from LLM-capable hardware in rankings.

## General hardware discovery

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
- [ ] Add EOL lifecycle alerts and used-price watch thresholds.

## Cluster software

- [ ] Node daemon.
- [ ] Discovery and health protocol.
- [ ] OpenAI-compatible router.
- [ ] Automatic model and specialist-accelerator placement.
- [ ] Power-aware scheduling using measured benchmark records.
- [ ] llama.cpp RPC fallback.
- [ ] Runtime lifecycle management for Hailo, SOPHGO, Tenstorrent and FPGA workers.
- [ ] Separate always-on control plane from inference workers.
