# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-08-12

### Added

- Bounded asynchronous catalog discovery pipeline with generic JSON-feed, schema.org JSON-LD and optional process-isolated source adapters.
- Hierarchical source-agent workers, per-source URL subworkers and bounded queues/backpressure.
- Native pooled `aiohttp` networking with global/per-host caps, keep-alive/DNS reuse, response-size limits, retry/backoff/jitter and `Retry-After` handling.
- Conditional HTTP cache with `ETag` / `Last-Modified`, parsed-observation reuse, TTL expiration, LRU-style pruning, bounded entry count and optional gzip persistence.
- AIMD-like adaptive source concurrency, per-source circuit breakers and adaptive observation batch sizing driven by latency/RSS pressure.
- True streaming large-JSON source ingestion through `ijson`.
- Persistent `llm-cluster-service` operation with health/readiness/status endpoints, dependency-light Prometheus metrics and hardened systemd installation.
- Incremental discovery/history writes, persistent single-writer SQLite/WAL state, bounded streaming transforms and normalized disk spooling.
- Original durable v1 distributed source-worker backend with cycles, leases, heartbeats, lease reclamation, retry attempts and idempotent batch IDs.
- **Secure v2 distributed coordinator protocol** with separate admin bearer authorization and replay-protected per-worker HMAC identity.
- TLS server/client support plus optional mutual-TLS worker certificates for secure coordinator deployments.
- `llm-cluster-distributed init-auth` for mode-`0600` generated admin/worker credentials without printing generated secrets.
- Leader-lease/epoch fencing so stale coordinators and old worker leases cannot mutate task state after active/standby failover.
- Automatic secure distributed cycles inside `llm-cluster-service`: submit, wait, streamed collection and canonical history persistence happen in one recurring daemon cycle.
- SHA-256 content-addressed remote result batches with idempotent `(task_id,batch_id)` insertion and NDJSON result streaming that avoids complete-cycle materialization.
- Worker capability advertisements, key/value locality labels, source affinity and bounded work stealing.
- CPU load, available-memory, Linux thermal and optional operator-supplied power/energy resource snapshots for lease eligibility.
- Worker drain/self-drain, cycle cancellation, failure quarantine and documented rolling-restart behavior.
- Live coordinator SQLite backup, offline atomic restore and shared-state active/standby promotion without making canonical catalog history multi-master.
- Optional native OTLP/HTTP traces/counters through the `telemetry` extra while retaining Prometheus as the default metrics path.
- Shared immutable SHA-256 source snapshots for normal full-body HTTP fetches with explicit freshness-bounded replay.
- Deterministic distributed fault smoke suite for worker crashes, coordinator restart persistence, stale-epoch fencing and backups.
- Hardware-class synthetic runtime baseline gate alongside the broad generic shared-runner performance floor.
- Runtime telemetry for source timing, HTTP attempts/retries/rate limits/bytes/cache hits, circuit state, batch targets and distributed cycle information.
- CI async-blocking guard across local, resilient, secure-distributed and daemon paths.
- Explicit-FX CAD landed-cost planning, catalog reports, sourced performance records, confidence-aware measured ranges and safe model-fit presets.
- Ground-up catalog dashboard redesign with Overview → Browse → Inspect → Compare, structured evidence/deployment detail, responsive navigation and safe embedded data.
- `docs/DASHBOARD.md`, `docs/DISTRIBUTED_RUNTIME.md` and `docs/DISTRIBUTED_SECURITY.md` defining UX, runtime, trust, failover and evidence boundaries.
- Tests for discovery, cache/retry/adaptive/circuit behavior, streaming, service health, process isolation, v1 leases, secure HMAC/replay, capability/resource scheduling, leader epochs, content-addressed results, cancellation/reclaim/backup, daemon distributed cycles and dashboard rendering.

### Changed

- Replaced thread-wrapped discovery HTTP with native async pooled networking.
- JSON/HTML parsing, normalization, filesystem work and SQLite work stay off the asyncio event loop.
- Discovery concurrency is independently bounded for agents, source subworkers, HTTP, transforms and queues.
- Repeatedly failing sources cool down instead of consuming service workers indefinitely.
- Failed/canceled local or remote sources do not participate in disappearance detection for that cycle.
- Very large JSON feeds can stream from HTTP instead of materializing the complete decoded document.
- Secure distributed collection now streams bounded result batches from content-addressed artifacts rather than returning one full-cycle JSON document.
- Distributed workers remain staging/source executors; canonical history and promotion remain collector responsibilities.
- `llm-cluster-service` can switch from local execution to authenticated v2 remote execution through `--distributed-coordinator` without changing canonical output semantics.
- `llm-cluster-install-service` accepts distributed coordinator, token-file, TLS and OTLP options so secure automatic cycles can run under systemd.
- Source configuration can express worker capability/label/resource requirements and affinity.
- Explicit CPU, thermal, available-memory and power scheduling constraints now reject workers that cannot report the required measurement; unknown telemetry is not treated as satisfying a hard limit.
- The coordinator can run active/standby with epoch fencing; documentation explicitly distinguishes this from quorum consensus or SQLite multi-master replication.
- Source snapshots and result payloads can share immutable content-addressed storage while preserving explicit source freshness semantics.
- The catalog dashboard is a structured research console instead of one dense table/filter bar; unknown/evidence boundaries stay explicit.
- Catalog shortlist scoring remains separate from measured performance and board-memory evidence remains distinct from CPU-theoretical maximums.
- `TODO.md` marks the secure/automatic distributed phase complete and moves next runtime work to credential/certificate rotation, external CAS/consensus backends, scheduler learning, disaster recovery, soak/chaos testing and cluster enrollment.
- Benchmarking remains optional and specialist metrics remain isolated from LLM throughput.

## [0.4.1] - 2026-08-10

### Changed

- Re-centered the project on its original purpose: product catalog, sourcing, pricing, compatibility and buying decisions.
- Demoted the v0.4 benchmark harness to optional evidence tooling; physical hardware ownership is not required for catalog inclusion.
- Reframed `llm-cluster rank` as a catalog/buying shortlist rather than pseudo-performance ranking.
- Corrected memory semantics so barebones no longer appear to include the CPU's theoretical maximum RAM.

### Added

- Explicit performance provenance vocabulary: local/community/vendor measured, derived/spec-based estimate, or unknown.
- `specs/EVIDENCE.md` with confidence and estimation guardrails.
- `llm-cluster list` filtering by category, budget and memory.
- `llm-cluster show` for product/evidence inspection.
- `llm-cluster fit` for conservative model-weight capacity screening without predicting tokens/sec.
- Separate `max_memory_gb` / `memory_config_status` semantics and memory-evidence weighting.

## [0.4.0] - 2026-08-10

### Added

- Measured-performance benchmark harness with a dedicated `llm-cluster-bench` CLI.
- Native asynchronous `llama-bench` JSON adapter with separate prefill and decode benchmark phases.
- Normalized vendor-runtime JSON bridges for Hailo, SOPHGO LLM-TPU, Tenstorrent TT-Metal and FPGA-native/Vitis-style experiments.
- Workload-specific specialist benchmark path for vision, audio, embeddings and other non-LLM accelerators.
- Benchmark profile, vendor adapter-output and measured-result JSON schemas.
- Asynchronous power sampling through external meter commands plus explicitly manual measured-power input.
- Power-boundary guardrail: canonical tokens/joule and specialist units/joule require `complete_node_input` scope.
- Model artifact hashing, file-size fit screening and separate runtime-verified fit status.
- Complete-system acquisition-cost handling and throughput-per-purchase-dollar metrics.
- Result comparison that groups incompatible model/workload signatures instead of ranking them together.
- Example benchmark profiles for llama.cpp CPU/Vulkan, Hailo-10H, SOPHGO, Tenstorrent, FPGA research and specialist vision.
- Benchmark contract validation in CI and benchmark harness documentation.

### Changed

- Benchmark schema upgraded to v2 and preserves raw samples, statistics, power scope and workload class.
- Benchmark/release agent skills enforce complete-node power and workload-comparability rules.
- v0.4 roadmap milestone is the implementation baseline; real hardware result collection remains a measurement phase.

## [0.3.0] - 2026-08-10

### Added

- First-class NPU, TPU, AI ASIC, FPGA/adaptive-SoC and decommissioned-accelerator catalog categories.
- Hailo-10H / Raspberry Pi AI HAT+ 2, SOPHGO BM1688 and BM1684X, Tenstorrent Wormhole n150s, AMD Kria KV260, AMD Versal AI Edge Gen 2, AMD Alveo V70, Google Coral Edge TPU, MemryX MX3 and Intel NCS2 reference entries.
- `docs/ACCELERATORS.md` with workload-routing, TOPS guardrails and accelerator benchmark requirements.
- Reusable `accelerator-research` agent skill.
- Accelerator metadata for family, host mode, software stack, LLM support, lifecycle, precision formats, power scope and workload role.
- Catalog schema v3 support for unresolved/EOL pricing without fake zero-dollar values.
- Modular catalog manifest plus category-sized JSON fragments to reduce merge conflicts as the hardware universe grows.

### Changed

- Screening and BOM code handles unresolved prices safely.
- LLM screening explicitly excludes TOPS/TFLOPS from the heuristic.
- Fixed-function vision accelerators are cataloged as specialists rather than mislabeled LLM workers.
- Project charter and guardrails cover accelerator power boundaries, runtime evidence and lifecycle risk.

## [0.2.0] - 2026-08-10

### Added

- Expanded project scope from Ryzen laptop-class nodes to heterogeneous mini PCs, development boards, SBCs, embedded boards and specialty compute.
- AMD BC-250 experimental candidate with explicit community-evidence and risk labels.
- NVIDIA Jetson Orin Nano Super, Orange Pi 5 Plus 32GB, Radxa ROCK 5 ITX+ 32GB, MINISFORUM BD795M, Framework Ryzen AI mainboard and Intel N100 control-plane references.
- Project charter and mechanical guardrails.
- Hardware catalog, benchmark, scoring and agent-workflow specifications.
- Five reusable agent skills for hardware research, catalog curation, benchmarking, architecture review and release governance.
- PR and hardware-candidate templates.
- Mechanical version/document governance check in CI.

### Changed

- Screening score supports heterogeneous hardware and avoids CPU-core-based cross-architecture performance claims.
- Parts table supports Alibaba, AliExpress and manufacturer/reference sources instead of labelling every URL as Alibaba.

## [0.1.0] - 2026-08-10

### Added

- Initial low-power distributed LLM cluster architecture.
- Alibaba hardware-market snapshot with prices, URLs, seller verification state and plain-language rationale.
- Ryzen 7 7735U, Ryzen 7 8845HS, Ryzen 7 8745HS and Ryzen AI 9 HX 370 node candidates.
- 2.5GbE switch, DDR5 SO-DIMM and NVMe sourcing leads.
- ASCII architecture, power, networking and model-placement diagrams.
- Machine-readable `data/parts.json` catalog.
- CLI node-ranking and BOM calculations.
- Catalog validation, stale-price checks and generated PARTS.md workflow.
- GitHub Actions validation workflow.
