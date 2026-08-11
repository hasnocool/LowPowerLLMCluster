# Firmware support endpoints and boot readiness

CPU/socket compatibility is not enough to guarantee that a motherboard will boot a selected CPU. This layer turns manufacturer firmware evidence into an explicit boot-readiness signal.

## Support-endpoint discovery

`firmware_readiness.discover_support_endpoints()` scans a verified manufacturer product page for same-manufacturer links that look like:

- CPU / processor support lists
- BIOS / UEFI / firmware pages
- support/download pages

Third-party links are rejected. Candidate endpoints are scored and bounded so the project can later fetch the most likely CPU-support/API/download surfaces without unrestricted crawling.

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

Absence from an unproven support table remains unresolved. Only evidence explicitly marked complete may turn an absent CPU into an unsupported result.

## Future enrichment

The next refinements are manufacturer-specific support APIs/pagination, BIOS download history, motherboard hardware revision mapping, and seller evidence for shipped BIOS version. Those must remain evidence-backed; chipset age is not a substitute for firmware proof.
