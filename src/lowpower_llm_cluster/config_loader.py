from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PUBLIC_REGISTRY = "public_sources.extra.json"
DEFAULT_CONFIG_NAME = "discovery.example.json"
LOCAL_CONFIG_NAME = "discovery.local.json"
DEFAULT_AUTO_SOURCE_EXPANSION: dict[str, Any] = {
    "enabled": True,
    "max_announcements_per_cycle": 16,
    "max_links_per_announcement": 8,
    "max_domains_per_cycle": 6,
    "max_surface_probes_per_domain": 8,
    "max_verified_products_per_cycle": 24,
    "max_dynamic_sources": 64,
    "min_dynamic_source_score": 0.72,
    "max_candidate_pages_per_dynamic_source": 24,
    "announcement_workers": 2,
    "dynamic_subworkers": 2,
    "probe_concurrency": 2,
    "verified_product_trust": 0.92,
}
DEFAULT_SOURCE_QUALITY_LEARNING: dict[str, Any] = {
    "enabled": True,
    "adaptive_scheduling": True,
    "min_cycles_before_adaptation": 3,
    "max_scan_every_cycles": 4,
    "min_budget_multiplier": 0.5,
    "max_budget_multiplier": 1.5,
    "max_candidate_pages_cap": 96,
    "debug_snapshot_limit": 500,
}
DEFAULT_DEBUG_ARTIFACTS: dict[str, Any] = {
    "root": "results/debug",
    "max_log_bytes": 8388608,
    "keep_runs": 20,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_sources(payload: Any, *, path: Path) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = payload.get("sources", [])
    else:
        raise ValueError(f"source registry {path} must contain an object or list")
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise ValueError(f"source registry {path} must contain a sources array of objects")
    return [dict(item) for item in values]


def _merge_sources(base: list[dict[str, Any]], override: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge source arrays by name while preserving base order and allowing local overrides."""
    merged = [dict(item) for item in base]
    positions = {str(item.get("name", "")): index for index, item in enumerate(merged)}
    for item in override:
        value = dict(item)
        name = str(value.get("name", ""))
        if name in positions:
            merged[positions[name]] = value
        else:
            positions[name] = len(merged)
            merged.append(value)
    return merged


def _inherit_local_config(config_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Make discovery.local.json a true local override of discovery.example.json.

    This prevents deployments from silently losing the large default/public source pool
    merely because the service points at an untracked local configuration file.
    Set ``inherit_default_config`` to false for an intentionally isolated local config.
    """
    if config_path.name != LOCAL_CONFIG_NAME or payload.get("inherit_default_config", True) is False:
        return dict(payload), []
    base_path = config_path.with_name(DEFAULT_CONFIG_NAME)
    if not base_path.exists():
        return dict(payload), []
    base_payload = _read_json(base_path)
    if not isinstance(base_payload, dict):
        raise ValueError(f"default discovery config {base_path} must contain a JSON object")
    merged = dict(base_payload)
    merged.update(payload)
    merged["sources"] = _merge_sources(
        _registry_sources({"sources": base_payload.get("sources", [])}, path=base_path),
        _registry_sources({"sources": payload.get("sources", [])}, path=config_path),
    )
    base_files = [str(value) for value in base_payload.get("source_files", ())]
    local_files = [str(value) for value in payload.get("source_files", ())]
    merged["source_files"] = list(dict.fromkeys([*base_files, *local_files]))
    return merged, [str(base_path.resolve())]


def load_discovery_config(path: Path | str) -> dict[str, Any]:
    """Load a discovery config and merge one or more external source registries.

    ``discovery.example.json`` loads the full default public registry. A sibling
    ``discovery.local.json`` inherits that default configuration by default and can
    override individual settings/sources without dropping public discovery coverage.
    Arbitrary custom configs remain explicit and isolated.
    """

    config_path = Path(path)
    payload = _read_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"discovery config {config_path} must contain a JSON object")
    config, inherited = _inherit_local_config(config_path, payload)
    sources = _registry_sources({"sources": config.get("sources", [])}, path=config_path)

    source_files = [str(value) for value in config.get("source_files", ())]
    default_registry = config_path.with_name(DEFAULT_PUBLIC_REGISTRY)
    if config_path.name in {DEFAULT_CONFIG_NAME, LOCAL_CONFIG_NAME} and config.get("inherit_default_config", True) is not False:
        if default_registry.exists() and DEFAULT_PUBLIC_REGISTRY not in source_files:
            source_files.append(DEFAULT_PUBLIC_REGISTRY)
        config.setdefault("auto_source_expansion", dict(DEFAULT_AUTO_SOURCE_EXPANSION))
        config.setdefault("source_quality_learning", dict(DEFAULT_SOURCE_QUALITY_LEARNING))
        config.setdefault("debug_artifacts", dict(DEFAULT_DEBUG_ARTIFACTS))

    loaded: list[str] = []
    for raw in source_files:
        registry_path = Path(raw)
        if not registry_path.is_absolute():
            registry_path = config_path.parent / registry_path
        registry_path = registry_path.resolve()
        registry = _read_json(registry_path)
        registry_sources = _registry_sources(registry, path=registry_path)
        existing_names = {str(item.get("name", "")) for item in sources}
        duplicates = sorted(existing_names & {str(item.get("name", "")) for item in registry_sources})
        if duplicates:
            raise ValueError(f"duplicate discovery source names: {', '.join(duplicates)}")
        sources.extend(registry_sources)
        loaded.append(str(registry_path))

    seen: set[str] = set()
    duplicates: list[str] = []
    for source in sources:
        name = str(source.get("name", "")).strip()
        if not name:
            raise ValueError("every discovery source requires a non-empty name")
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise ValueError(f"duplicate discovery source names: {', '.join(sorted(set(duplicates)))}")

    warnings: list[str] = []
    if config_path.name in {DEFAULT_CONFIG_NAME, LOCAL_CONFIG_NAME} and len(sources) < 10:
        warnings.append(f"only {len(sources)} discovery sources loaded; expected the default public source pool")
    config["sources"] = sources
    config["source_registry_files"] = loaded
    config["inherited_config_files"] = inherited
    config["config_warnings"] = warnings
    return config
