from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PUBLIC_REGISTRY = "public_sources.extra.json"


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


def load_discovery_config(path: Path | str) -> dict[str, Any]:
    """Load a discovery config and merge one or more external source registries.

    ``source_files`` entries are resolved relative to the main config. The standard
    sibling ``public_sources.extra.json`` is auto-loaded when present so the default
    installation can grow its public source pool without bloating the core config.
    Duplicate source names are rejected before any network activity begins.
    """

    config_path = Path(path)
    payload = _read_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"discovery config {config_path} must contain a JSON object")
    config = dict(payload)
    sources = _registry_sources({"sources": config.get("sources", [])}, path=config_path)

    source_files = [str(value) for value in config.get("source_files", ())]
    default_registry = config_path.with_name(DEFAULT_PUBLIC_REGISTRY)
    if default_registry.exists() and DEFAULT_PUBLIC_REGISTRY not in source_files:
        source_files.append(DEFAULT_PUBLIC_REGISTRY)

    loaded: list[str] = []
    for raw in source_files:
        registry_path = Path(raw)
        if not registry_path.is_absolute():
            registry_path = config_path.parent / registry_path
        registry_path = registry_path.resolve()
        registry = _read_json(registry_path)
        sources.extend(_registry_sources(registry, path=registry_path))
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

    config["sources"] = sources
    config["source_registry_files"] = loaded
    return config
