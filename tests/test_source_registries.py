from __future__ import annotations

import json
from pathlib import Path

import pytest

from lowpower_llm_cluster.config_loader import load_discovery_config

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "discovery.example.json"
EXTRA_REGISTRY = ROOT / "config" / "public_sources.extra.json"
PUBLIC_TYPES = {"html_index", "sitemap", "feed", "announcement_index"}


def test_default_config_auto_loads_extra_public_registry() -> None:
    merged = load_discovery_config(DEFAULT_CONFIG)
    registry = json.loads(EXTRA_REGISTRY.read_text(encoding="utf-8"))
    names = [source["name"] for source in merged["sources"]]

    assert len(registry["sources"]) >= 40
    assert len(merged["sources"]) >= 70
    assert len(names) == len(set(names))
    assert any(path.endswith("public_sources.extra.json") for path in merged["source_registry_files"])


def test_local_config_inherits_full_default_pool_and_overrides_sources(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_payload = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    registry_payload = json.loads(EXTRA_REGISTRY.read_text(encoding="utf-8"))
    (config_dir / "discovery.example.json").write_text(json.dumps(default_payload), encoding="utf-8")
    (config_dir / "public_sources.extra.json").write_text(json.dumps(registry_payload), encoding="utf-8")
    local = {
        "http_concurrency": 3,
        "sources": [
            {"name": "manufacturer-pages", "type": "jsonld", "urls": ["https://example.test/product"]},
            {"name": "local-test-feed", "type": "json", "endpoint": "http://127.0.0.1:8765/catalog.json"},
        ],
    }
    local_path = config_dir / "discovery.local.json"
    local_path.write_text(json.dumps(local), encoding="utf-8")

    merged = load_discovery_config(local_path)
    names = [source["name"] for source in merged["sources"]]
    manufacturer = next(source for source in merged["sources"] if source["name"] == "manufacturer-pages")
    assert merged["http_concurrency"] == 3
    assert len(merged["sources"]) >= 70
    assert "local-test-feed" in names
    assert manufacturer["urls"] == ["https://example.test/product"]
    assert len(names) == len(set(names))
    assert merged["inherited_config_files"]
    assert not merged["config_warnings"]


def test_local_config_can_explicitly_opt_out_of_inheritance(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "discovery.example.json").write_text(DEFAULT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    local_path = config_dir / "discovery.local.json"
    local_path.write_text(json.dumps({
        "inherit_default_config": False,
        "sources": [{"name": "local-only", "type": "jsonld", "urls": ["https://example.test/product"]}],
    }), encoding="utf-8")
    loaded = load_discovery_config(local_path)
    assert [source["name"] for source in loaded["sources"]] == ["local-only"]
    assert loaded["inherited_config_files"] == []


def test_extra_registry_is_bounded_https_and_credential_free() -> None:
    registry = json.loads(EXTRA_REGISTRY.read_text(encoding="utf-8"))
    forbidden = ("api_key", "apikey", "credential", "access_token", "client_secret", "password")
    classes = {source.get("source_class") for source in registry["sources"]}

    assert {"industrial_edge", "jetson_ecosystem", "fpga_accelerator", "refurbished_enterprise", "public_distributor", "vendor_release_feed"} <= classes
    for source in registry["sources"]:
        assert source["type"] in PUBLIC_TYPES
        assert source.get("same_host") is True
        assert 1 <= int(source["max_index_pages"]) <= 4
        assert 1 <= int(source["max_candidate_pages"]) <= 120
        assert 1 <= int(source["subworkers"]) <= 4
        assert source.get("include_patterns")
        assert all(str(seed).startswith("https://") for seed in source["seeds"])
        assert not any(fragment in json.dumps(source).lower() for fragment in forbidden)


def test_explicit_registry_files_and_duplicate_names(tmp_path: Path) -> None:
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({"sources": [{"name": "extra", "type": "html_index"}]}), encoding="utf-8")
    config = tmp_path / "discovery.json"
    config.write_text(json.dumps({"source_files": ["extra.json"], "sources": [{"name": "base", "type": "jsonld"}]}), encoding="utf-8")

    loaded = load_discovery_config(config)
    assert [source["name"] for source in loaded["sources"]] == ["base", "extra"]

    extra.write_text(json.dumps({"sources": [{"name": "base", "type": "html_index"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate discovery source names"):
        load_discovery_config(config)
