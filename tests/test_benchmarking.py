# tests/test_benchmarking.py
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from lowpower_llm_cluster.benchmarking.models import MetricSummary
from lowpower_llm_cluster.benchmarking.runner import comparable_signature, run_profile, validate_profile


def test_metric_summary_uses_median_and_preserves_samples() -> None:
    summary = MetricSummary.from_values([10.0, 12.0, 11.0], "tokens/s")
    assert summary.median == 11.0
    assert summary.mean == 11.0
    assert summary.samples == [10.0, 12.0, 11.0]


def test_profile_requires_three_runs() -> None:
    profile = {
        "schema_version": 1,
        "hardware_id": "x",
        "workload_class": "vision",
        "adapter": {"type": "json_command", "command": ["echo"]},
        "model": {"name": "m", "quantization": "int8"},
        "workload": {"runs": 2},
    }
    with pytest.raises(ValueError, match="at least 3"):
        validate_profile(profile)


def test_vendor_bridge_specialist_efficiency_requires_complete_node_power(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import json\n"
        "print(json.dumps({'fit_status':'runtime_verified','metadata':{'runtime_version':'test'},"
        "'metrics':{'frames_per_second':{'unit':'frames/s','samples':[90, 92, 91]}}}))\n",
        encoding="utf-8",
    )
    profile = {
        "schema_version": 1,
        "hardware_id": "accel-google-coral-usb",
        "workload_class": "vision",
        "primary_metric": "frames_per_second",
        "system_cost_usd": 100,
        "adapter": {"type": "json_command", "command": [sys.executable, str(bridge)]},
        "model": {"name": "vision", "quantization": "INT8"},
        "workload": {"runs": 3},
        "power": {
            "provider": "static_measured",
            "scope": "complete_node_input",
            "source": "test meter",
            "watts_by_phase": {"active": 10.0},
        },
    }
    result = asyncio.run(run_profile(profile))
    assert result["fit"]["runtime"]["status"] == "runtime_verified"
    assert result["metrics"]["frames_per_second"]["median"] == 91.0
    assert result["efficiency"]["primary_units_per_joule"] == pytest.approx(9.1)
    assert result["efficiency"]["primary_units_per_purchase_usd"] == pytest.approx(0.91)


def test_board_only_power_does_not_create_canonical_energy_metric(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import json\nprint(json.dumps({'metrics':{'frames_per_second':{'unit':'frames/s','samples':[100,100,100]}}}))\n",
        encoding="utf-8",
    )
    profile = {
        "schema_version": 1,
        "hardware_id": "accel-google-coral-usb",
        "workload_class": "vision",
        "primary_metric": "frames_per_second",
        "system_cost_usd": 100,
        "adapter": {"type": "json_command", "command": [sys.executable, str(bridge)]},
        "model": {"name": "vision", "quantization": "INT8"},
        "workload": {"runs": 3},
        "power": {
            "provider": "static_measured",
            "scope": "accelerator_board",
            "source": "board telemetry",
            "watts_by_phase": {"active": 2.0},
        },
    }
    result = asyncio.run(run_profile(profile))
    assert "primary_units_per_joule" not in result["efficiency"]


def test_comparison_signature_separates_quantization() -> None:
    base = {
        "workload_class": "llm",
        "model": {"name": "m", "sha256": "abc", "quantization": "Q4"},
        "workload": {"context_tokens": 4096, "prompt_tokens": 512, "generated_tokens": 128},
        "efficiency": {},
    }
    other = json.loads(json.dumps(base))
    other["model"]["quantization"] = "Q8"
    assert comparable_signature(base) != comparable_signature(other)


def test_llama_cpp_adapter_parses_native_json_and_phase_power(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"fake-gguf-for-test")
    fake_bench = tmp_path / "llama-bench"
    fake_bench.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args=sys.argv\n"
        "p=int(args[args.index('-p')+1])\n"
        "n=int(args[args.index('-n')+1])\n"
        "samples=[101.0, 103.0, 102.0] if p else [11.0, 12.0, 13.0]\n"
        "row={'build_commit':'test123','build_number':1,'cpu_info':'fake cpu','gpu_info':'',"
        "'backends':'CPU','model_type':'fake','model_n_params':1000,'n_gpu_layers':0,'n_threads':4,"
        "'n_prompt':p,'n_gen':n,'avg_ts':sum(samples)/len(samples),'samples_ts':samples}\n"
        "print(json.dumps([row]))\n",
        encoding="utf-8",
    )
    fake_bench.chmod(0o755)
    profile = {
        "schema_version": 1,
        "hardware_id": "node-huake-7735u-barebone",
        "configuration_id": "test-cpu",
        "workload_class": "llm",
        "system_cost_usd": 200,
        "adapter": {"type": "llama_cpp", "binary": str(fake_bench), "backend": "CPU"},
        "model": {"name": "fake", "path": str(model), "quantization": "Q4_K_M"},
        "workload": {
            "context_tokens": 4096,
            "context_depth_tokens": 512,
            "prompt_tokens": 512,
            "generated_tokens": 128,
            "runs": 3,
        },
        "power": {
            "provider": "static_measured",
            "scope": "complete_node_input",
            "source": "test meter",
            "watts_by_phase": {"prefill": 20.0, "decode": 10.0},
        },
    }
    result = asyncio.run(run_profile(profile))
    assert result["runtime"]["runtime_name"] == "llama.cpp"
    assert result["runtime"]["runtime_version"] == "test123+1"
    assert result["metrics"]["prompt_tokens_per_second"]["median"] == 102.0
    assert result["metrics"]["generation_tokens_per_second"]["median"] == 12.0
    assert result["efficiency"]["prompt_tokens_per_joule"] == pytest.approx(5.1)
    assert result["efficiency"]["generation_tokens_per_joule"] == pytest.approx(1.2)
