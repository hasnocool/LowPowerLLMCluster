# Catalog Curation Skill

Use when adding, removing or refreshing hardware data.

- `data/parts.json` is authoritative; do not hand-edit generated `PARTS.md` as the source.
- Preserve the verification date and direct URL.
- Distinguish exact-SKU price from a variant family range.
- Keep secondary-market and sold-out references visible when they remain technically useful, but mark status accurately.
- Deduplicate by actual platform/configuration, not seller title.
- Run `python scripts/validate_catalog.py`, `python scripts/render_parts_table.py`, and governance checks.
