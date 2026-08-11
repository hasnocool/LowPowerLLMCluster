# Release Governance Skill

Use before merging or publishing a meaningful change.

1. Determine semantic-version impact.
2. Keep `VERSION`, `pyproject.toml`, package `__version__`, and latest CHANGELOG version aligned.
3. Update README/PARTS/TODO/specs when their truth changed.
4. Run `python scripts/check_governance.py`.
5. Run `python scripts/validate_catalog.py`.
6. Run `python scripts/validate_benchmark_profiles.py`.
7. Regenerate `PARTS.md` and require a clean diff on a second render.
8. Run tests.
9. Never merge known failing CI just to unblock a release.
