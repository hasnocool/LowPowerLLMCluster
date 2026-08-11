# Firmware support endpoints and boot readiness

CPU/socket compatibility is not enough to guarantee that a motherboard will boot a selected CPU. This layer turns manufacturer firmware evidence into an explicit boot-readiness signal.

## Linked support-endpoint discovery

`firmware_readiness.discover_support_endpoints()` scans a verified manufacturer product page for same-manufacturer CPU-support, BIOS/UEFI/firmware and download links. Third-party links are rejected.

## Unlinked support/API discovery

`firmware_discovery.py` adds a second bounded pass when linked evidence is incomplete. It can derive candidate official surfaces from:

- provider-specific support URL patterns for ASUS, MSI, Gigabyte/AORUS and ASRock;
- model/MPN tokens already verified on the product page;
- XHR/JSON/API URLs exposed inside manufacturer JavaScript;
- official `robots.txt` sitemap declarations;
- official sitemap entries matching the product model and support/CPU/BIOS paths.

Only HTTPS resources on the verified manufacturer host are eligible. Discovery is bounded (`MAX_DISCOVERY_FETCHES = 8`) and does not become an unrestricted crawler.

The strongest CPU matrix found is retained. A complete matrix beats partial/static evidence; a larger partial result may increase coverage but cannot claim completeness.

## Manufacturer support API / pagination ingestion

`manufacturer_support.ingest_support_endpoint()` normalizes common JSON/API and HTML-table shapes into pair-level CPU/BIOS rows. Traversal is bounded to 64 pages and remains on the verified host.

A matrix becomes `cpu_support_matrix_complete=true` only from explicit end-of-data evidence:

- explicit total-page count and final page reached;
- explicit total-row count and fetched range reaches that count;
- explicit `hasMore=false` / equivalent.

If an explicit total count disagrees with the final deduplicated rows, completeness is revoked. Short responses, empty next links and static HTML do not prove completeness.

## BIOS release history

Unlinked/linked BIOS API candidates are also inspected for release-history records. Normalized rows preserve:

- BIOS version;
- release date when supplied;
- official download URL when supplied;
- manufacturer source URL;
- source class and confidence.

The history is evidence, not a version-ordering oracle. Vendor-specific version comparators are required before arbitrary strings such as `A9`, `AB`, `F12`, or `7C56vAB` can be ordered safely.

## Hardware revision evidence

Verified manufacturer text can retain explicit PCB/board/hardware revision identifiers such as `Rev. 1.2`. Revision evidence is stored separately because a firmware history can differ across board revisions.

A manufacture date by itself is **not** used to infer either revision or shipped BIOS.

## BIOS Flashback / CPU-less update evidence

`detect_bios_flashback()` recognizes manufacturer feature names such as USB BIOS FlashBack, Flash BIOS Button, Q-Flash Plus and BIOS Flash Button. High-confidence CPU-less recovery still requires explicit wording equivalent to `without installing a CPU` / `no CPU required`.

The same verified text may also expose an explicit factory/shipped BIOS version. Statements such as `ships with BIOS A9 from factory` are retained; `manufactured 2025-08` or `latest BIOS AB` are not treated as shipped-firmware evidence.

## Boot-readiness score

`boot_readiness_score()` combines pair-level CPU/BIOS evidence, Flashback/recovery evidence, and explicit shipped-BIOS evidence.

Typical semantics:

- `0`: CPU explicitly unsupported;
- `~34`: support and recovery unresolved;
- `~48`: minimum BIOS required and no CPU-less path documented;
- `~62`: supported, but shipped BIOS/recovery unresolved;
- `~78`: Flashback documented, CPU-less behavior not explicit;
- `~88`: minimum BIOS may be needed and CPU-less recovery is explicitly documented;
- `~96`: support row requires no minimum BIOS;
- `98`: explicit shipped BIOS is proven sufficient.

For now, exact equality between shipped BIOS and minimum BIOS is sufficient proof. A different version string remains unresolved unless a manufacturer-specific comparator is implemented; lexical or date-based guessing is prohibited.

The score remains an installation/readiness signal, never a performance metric.

## Matrix completeness and pair semantics

Absence from an incomplete matrix remains unresolved. Absence from an explicitly complete manufacturer matrix may safely become unsupported under the existing CPU+motherboard pair rules.

## Remaining firmware accuracy work

The largest remaining gaps are vendor-specific BIOS version ordering, richer board-revision mapping, seller-side revision/BIOS evidence, and historical factory-shipping metadata where a manufacturer actually publishes it. These must remain evidence-backed; chipset age or manufacture date is not a substitute for firmware proof.
