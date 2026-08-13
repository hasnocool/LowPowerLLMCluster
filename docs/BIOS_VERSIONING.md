# Vendor BIOS versioning and board-revision history

BIOS strings are not globally sortable. The firmware layer compares versions only when manufacturer-specific semantics are known and conservative.

## Supported comparators

- MSI: same board-prefix `...vSUFFIX` releases use base-36 suffix ordering, allowing relationships such as `7C56vA9 < 7C56vAB`; different board prefixes are not comparable.
- Gigabyte/AORUS: `F<number>` releases compare numerically (`F12 < F14`). Letter-suffixed builds are treated as prerelease/beta variants of the same numeric release; the unsuffixed release sorts after its same-number lettered builds.
- ASUS: ordinary numeric BIOS releases compare numerically.
- ASRock: numeric versions compare only inside the same explicit series prefix, such as `P1.20 < P1.40`; cross-series comparisons such as `L3.01` versus `P1.20` remain unresolved.
- Unknown vendors: only exact equality is considered safe.

An unresolved comparison never becomes an implicit success.

## Revision-scoped history

`firmware_history.py` extracts BIOS history rows that explicitly identify PCB/board/hardware revisions and indexes them by revision. Unscoped BIOS rows are never silently assigned to a known board revision.

This allows evidence to represent relationships such as:

```text
Board rev 1.0 -> F12, F14
Board rev 1.2 -> F14, F15
```

without assuming all revisions share the same firmware train. Revision-scoped history is still not proof of the firmware installed at retail shipment; shipped BIOS requires explicit manufacturer/seller factory-version evidence.

## Boot readiness

When an explicit shipped BIOS and CPU-required minimum are available, `boot_readiness_score()` now uses the vendor comparator. A safely proven equal/newer shipped BIOS can establish firmware readiness. A safely proven older version lowers certainty and retains the firmware-update warning. Unknown version ordering remains unresolved and falls back to Flashback/CPU-less recovery evidence.
