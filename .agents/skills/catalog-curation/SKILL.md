# Catalog Curation Skill

Use for the project's primary workflow: discovering, adding, correcting or refreshing products.

1. Read the charter, guardrails, `specs/HARDWARE_CATALOG.md` and `specs/EVIDENCE.md`.
2. `data/parts.json` is the canonical manifest; reviewed records live under `data/catalog/*.json`.
3. Discovery observations/history are staging evidence, not automatic canonical truth.
4. Prefer the async discovery pipeline for current sources; keep blocking network/SQLite work off the event loop.
5. Preserve exact configuration, verification date, price/source URL and listing status.
6. Record source/seller/SKU confidence when the evidence supports it; never substitute seller confidence for exact-SKU confidence.
7. Distinguish included/fixed RAM from board-verified maximum and CPU theoretical maximum. Add board memory source URL/date when available.
8. Preserve dimensions, DC input, PSU/cooling and host requirements when those affect deployment.
9. Unknown performance is valid. Never fill missing throughput with TOPS-based arithmetic.
10. When real vendor/community/local performance exists, preserve model/runtime/workload/quantization/context provenance. Multi-source ranges require compatible independent measured sources.
11. Keep specialist vision/audio metrics separate from LLM throughput.
12. Keep sold-out/EOL references when technically useful, but mark lifecycle/availability accurately and track used-market price history separately.
13. Regenerate `PARTS.md` after canonical catalog changes and run catalog/governance/tests.
14. Update README, CHANGELOG, TODO and relevant specs whenever behavior changes.
