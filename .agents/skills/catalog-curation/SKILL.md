# Catalog Curation Skill

Use for the project's primary workflow: adding, correcting or refreshing products.

1. Read the charter, guardrails, `specs/HARDWARE_CATALOG.md` and `specs/EVIDENCE.md`.
2. `data/parts.json` is the manifest; editable records live under `data/catalog/*.json`.
3. Preserve exact configuration, verification date, price/source URL and listing status.
4. Distinguish included/fixed RAM from configurable board maximum and CPU theoretical maximum.
5. Unknown performance is valid. Never fill missing throughput with TOPS-based arithmetic.
6. When real vendor/community/local performance exists, attach provenance/confidence rather than copying a naked number.
7. Keep sold-out/EOL references when technically useful, but mark lifecycle/availability accurately.
8. Regenerate `PARTS.md` and run catalog/governance/tests.
