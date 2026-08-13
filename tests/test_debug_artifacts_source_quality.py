from __future__ import annotations

import asyncio
import json
from pathlib import Path

from lowpower_llm_cluster.config_loader import load_discovery_config
from lowpower_llm_cluster.debug_artifacts import DebugArtifactWriter, export_repo_debug_bundle, sanitize
from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.service_install import render_systemd_unit
from lowpower_llm_cluster.source_quality import SourceQualitySample, SourceQualityStore
from lowpower_llm_cluster.streaming_discovery import StreamingDiscoveryPipeline

ROOT = Path(__file__).resolve().parents[1]


def test_sanitize_redacts_secret_keys_values_and_url_queries() -> None:
    payload = sanitize({
        "api_key": "sk-abcdefghijklmnop123456",
        "nested": {"Authorization": "Bearer abcdefghijklmnop"},
        "url": "https://example.test/products?token=secret-value&part=42",
        "hf": "hf_abcdefghijklmnopqrstuvwxyz",
    })
    rendered = json.dumps(payload)
    assert "abcdefghijklmnop123456" not in rendered
    assert "abcdefghijklmnop" not in rendered
    assert "secret-value" not in rendered
    assert "abcdefghijklmnopqrstuvwxyz" not in rendered
    assert "part=42" in payload["url"]
    assert "[REDACTED]" in rendered


def test_debug_writer_and_repo_export_are_sanitized(tmp_path: Path) -> None:
    async def scenario() -> None:
        debug = tmp_path / "debug"
        writer = DebugArtifactWriter(debug, keep_runs=2)
        await writer.emit("request_failed", api_key="sk-abcdefghijklmnop123456", url="https://example.test/?token=hidden&x=1")
        await writer.write_run(
            "run-1",
            summary={"run_id": "run-1", "authorization": "Bearer verysecretvalue"},
            source_quality=[{"source": "auto-test", "quality_score": 0.7}],
            scheduler={"selected_sources": 1},
            effective_config={"password": "do-not-publish", "sources": []},
        )

        history = tmp_path / "history.sqlite3"
        store = SourceQualityStore(history)
        await store.initialize()
        await store.record([SourceQualitySample(
            source="auto-test", success=True, raw_observations=4, unique_observations=4,
            priced_observations=4, spec_score_sum=3.0, freshness_score_sum=3.0,
            relevance_score_sum=3.0, latency_ms=100.0,
        )])
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"api_key": "sk-abcdefghijklmnop123456", "sources": []}), encoding="utf-8")
        events = tmp_path / "events.jsonl"
        events.write_text(json.dumps({"event": "x", "token": "hidden"}) + "\n", encoding="utf-8")
        latest = tmp_path / "latest.json"
        latest.write_text(json.dumps({"authorization": "Bearer anothersecret"}), encoding="utf-8")
        bundle = export_repo_debug_bundle(
            destination=tmp_path / "repo-debug",
            debug_dir=debug,
            history=history,
            config=config,
            event_log=events,
            latest_output=latest,
            tail_lines=50,
        )
        combined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in bundle.iterdir() if path.is_file())
        assert "abcdefghijklmnop123456" not in combined
        assert "do-not-publish" not in combined
        assert "anothersecret" not in combined
        assert (bundle / "manifest.json").exists()
        assert (bundle / "source-quality.json").exists()
        assert (debug / "runs" / "run-1" / "scheduler.json").exists()

    asyncio.run(scenario())


def test_source_quality_waits_for_history_then_diverges(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SourceQualityStore(tmp_path / "quality.sqlite3", min_cycles_before_adaptation=3, max_scan_every_cycles=4)
        await store.initialize()
        high = SourceQualitySample(
            source="auto-high", success=True, raw_observations=24, unique_observations=24,
            priced_observations=24, spec_score_sum=22.0, freshness_score_sum=22.0,
            relevance_score_sum=22.0, latency_ms=150.0,
        )
        low = SourceQualitySample(
            source="auto-low", success=False, raw_observations=20, unique_observations=1,
            priced_observations=0, spec_score_sum=0.1, freshness_score_sum=0.1,
            relevance_score_sum=0.0, latency_ms=9000.0, error="timeout",
        )
        await store.record([high, low])
        first = await store.policies(["auto-high", "auto-low"])
        assert first["auto-high"]["scan_every_cycles"] == 1
        assert first["auto-low"]["scan_every_cycles"] == 1
        assert first["auto-high"]["budget_multiplier"] == 1.0
        assert first["auto-low"]["budget_multiplier"] == 1.0

        await store.record([high, low])
        await store.record([high, low])
        final = await store.policies(["auto-high", "auto-low"])
        assert final["auto-high"]["quality_score"] > final["auto-low"]["quality_score"]
        assert final["auto-high"]["budget_multiplier"] > 1.0
        assert final["auto-low"]["scan_every_cycles"] >= 3
        assert final["auto-low"]["budget_multiplier"] < 1.0

    asyncio.run(scenario())


def test_streaming_pipeline_reports_raw_unique_and_duplicate_rate() -> None:
    class DuplicateAdapter:
        name = "duplicates"

        async def discover_batches(self):
            item = ProductObservation(source=self.name, source_id="one", listing_url="https://example.test/one", title="GPU")
            yield (item, item)
            yield (item,)

    async def scenario() -> None:
        pipeline = StreamingDiscoveryPipeline([DuplicateAdapter()], worker_count=1)
        records = []
        async for batch in pipeline.stream():
            records.extend(batch.observations)
        assert len(records) == 1
        assert pipeline.last_metrics["source_raw_observations"]["duplicates"] == 3
        assert pipeline.last_metrics["source_unique_observations"]["duplicates"] == 1
        assert pipeline.last_metrics["source_duplicate_rates"]["duplicates"] == 0.666667

    asyncio.run(scenario())


def test_default_config_enables_learning_and_debug_artifacts() -> None:
    config = load_discovery_config(ROOT / "config" / "discovery.example.json")
    assert config["source_quality_learning"]["enabled"] is True
    assert config["source_quality_learning"]["adaptive_scheduling"] is True
    assert config["debug_artifacts"]["keep_runs"] >= 1


def test_systemd_unit_wires_debug_directory() -> None:
    unit = render_systemd_unit(
        service_command="llm-cluster-service",
        config="/repo/config.json",
        history="/repo/results/history.sqlite3",
        output="/repo/results/latest.json",
        cache="/repo/results/cache.json",
        event_log="/repo/results/events.jsonl",
        debug_dir="/repo/results/debug",
        interval=None,
    )
    assert "--debug-dir /repo/results/debug" in unit
