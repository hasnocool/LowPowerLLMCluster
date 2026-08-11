# Firmware support endpoints and boot readiness

CPU/socket compatibility is not enough to guarantee that a motherboard will boot a selected CPU. This layer turns manufacturer firmware evidence into an explicit boot-readiness signal.

## Support-endpoint discovery

`firmware_readiness.discover_support_endpoints()` scans a verified manufacturer product page for same-manufacturer links that look like:

- CPU / processor support lists
- BIOS / UEFI / firmware pages
- support/download pages

Third-party links are rejected. Candidate endpoints are scored and bounded so the project can fetch the most likely CPU-support/API/download surfaces without unrestricted crawling.

## Manufacturer support API / pagination ingestion

`manufacturer_support.ingest_support_endpoint()` and `ingest_ranked_support_endpoints()` fetch ranked CPU-support endpoints asynchronously and normalize common manufacturer JSON/API and HTML-table shapes into the same pair-level CPU/BIOS row format used by the build solver.

The ingestor recognizes ASUS, MSI, Gigabyte/AORUS and ASRock host families while retaining a conservative generic parser for other official manufacturers. The provider label identifies the parsing/evidence path; it does not relax source authority.

Network traversal is bounded to 64 pages and remains on the verified manufacturer's host. A `next` URL that escapes that host is not followed.

### Completeness proofs

A matrix becomes `cpu_support_matrix_complete=true` only when the endpoint supplies explicit pagination evidence proving the end of the dataset. Accepted proof classes are:

- explicit total-page count and the last page has been reached;
- explicit total-row count and the fetched page range reaches that count;
- explicit `hasMore=false` / equivalent end-of-pagination state.

When an explicit total row count is present, the final deduplicated matrix row count must equal it. A mismatch revokes completeness rather than silently trusting the response.

A static HTML support table, a short API response, an empty next link, or a page that simply returns fewer records than expected is **not** sufficient completeness proof.

During structured motherboard enrichment:

1. verified static HTML CPU/BIOS rows are retained first;
2. discovered official CPU-support endpoints are fetched with the existing async HTTP client;
3. a complete API matrix may replace the static matrix and set completeness true;
4. a larger partial API matrix may replace a smaller static matrix to improve coverage but remains incomplete;
5. a smaller partial API result cannot erase stronger existing static coverage.

The selected endpoint, provider, attempts and completeness proof remain in `structured_document.support_api` for auditability.

## BIOS Flashback / CPU-less update evidence

`detect_bios_flashback()` recognizes explicit manufacturer feature names such as:

- USB BIOS FlashBack
- BIOS FlashBack
- Flash BIOS Button
- Q-Flash Plus
- BIOS Flash Button

A feature-name match alone is not treated as proof that a CPU-less update is possible. High confidence requires explicit text such as `without installing a CPU` / `no CPU required`.

## Boot-readiness score

`boot_readiness_score()` combines pair-level CPU/BIOS evidence with firmware recovery evidence.

Typical semantics:

- `0`: manufacturer evidence says the CPU is unsupported.
- `~34`: CPU support and recovery path unresolved.
- `~48`: CPU is supported only at/after a minimum BIOS, but evidence says no CPU-less recovery path exists.
- `~62`: CPU is supported at/after a minimum BIOS, but shipped BIOS and recovery capability are unknown.
- `~78`: Flashback-like capability is documented, but CPU-less operation is not explicit.
- `~88`: minimum BIOS may be required and manufacturer explicitly documents CPU-less update/recovery.
- `~96`: support evidence does not require a minimum BIOS.
- `98`: seller/manufacturer evidence explicitly proves the shipped BIOS meets the required minimum.

The score is a readiness/friction signal, not a performance score.

## Matrix completeness

Absence from an unproven support table remains unresolved. Once an explicitly complete manufacturer API matrix is persisted, absence can safely become an unsupported pair result under the existing compatibility semantics.

## Remaining enrichment

The next refinements are discovery of support/API surfaces that are not linked from the verified product page, BIOS download history, motherboard hardware revision mapping, and seller evidence for shipped BIOS version. Those must remain evidence-backed; chipset age is not a substitute for firmware proof.
