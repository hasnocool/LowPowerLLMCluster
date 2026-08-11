# Roadmap

## v0.1 — hardware planning foundation

- [x] machine-readable parts catalog
- [x] current Alibaba price/source snapshot
- [x] plain-language explanations and ASCII diagrams
- [x] transparent screening heuristic and BOM CLI
- [x] CI catalog validation

## v0.2 — heterogeneous hardware + governance

- [x] broaden scope to mini PCs, dev boards, SBCs, embedded and specialty boards
- [x] add BC-250, Jetson, RK3588 and mobile-CPU motherboard reference classes
- [x] project charter and guardrails
- [x] agent skills and workflow specs
- [x] mechanical release/document governance in CI
- [x] heterogeneous screening score that does not pretend core counts are cross-platform benchmarks

## v0.3 — measured performance

- [ ] benchmark JSON schema
- [ ] reproducible llama.cpp runner for CPU/Vulkan/CUDA and other usable backends
- [ ] idle/load wall-power collection
- [ ] tokens/joule, tokens/$ and model-capacity reports
- [ ] stock-vs-modified experimental hardware identities

## v0.4 — sourcing automation

- [ ] seller/URL history
- [ ] price history and currency normalization
- [ ] availability/MOQ tracking
- [ ] duplicate-listing detection
- [ ] supplier confidence and landed-cost scoring
- [ ] asynchronous, rate-limited source adapters

## v0.5 — cluster control plane

- [ ] node discovery and capability registry
- [ ] llama.cpp server lifecycle management
- [ ] workload-aware model placement
- [ ] queue-aware routing and automatic failover
- [ ] power-aware scheduling
- [ ] OpenAI-compatible gateway
- [ ] optional llama.cpp RPC orchestration for capacity-bound models

## v0.6 — dashboard

- [ ] web + CLI/TUI dashboards
- [ ] temperatures, power and model inventory
- [ ] prompt/decode throughput and tokens/joule
- [ ] hardware value and price-history views
- [ ] experimental-hardware risk/health view
