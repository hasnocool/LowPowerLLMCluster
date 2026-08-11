# Contributing

Hardware data changes should include a source URL, verification date, price range, MOQ and a short explanation of why the part is relevant.

Run before committing:

```bash
python scripts/validate_catalog.py
python scripts/render_parts_table.py
python -m pip install -e . pytest
pytest -q
```

If the change alters user-visible behavior or catalog structure, update `CHANGELOG.md`, `TODO.md` and the relevant documentation.
