# src/lowpower_llm_cluster/benchmarking/adapters.py
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .models import MetricSummary, PowerWindow
from .power import PowerProbe, run_process_with_power


@dataclass
class AdapterResult:
    metrics: dict[str, MetricSummary] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    fit_status: str = "unknown"
    power_windows: dict[str, PowerWindow] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterContext:
    profile: dict[str, Any]
    power_probe: PowerProbe | None
    power_interval_s: float
    timeout_s: float | None

    async def execute(self, phase: str, argv: list[str]) -> tuple[bytes, bytes, PowerWindow | None]:
        returncode, stdout, stderr, window = await run_process_with_power(
            argv,
            phase=phase,
            probe=self.power_probe,
            interval_s=self.power_interval_s,
            timeout_s=self.timeout_s,
        )
        if returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{phase} command failed with exit {returncode}: {message}")
        return stdout, stderr, window


class BenchmarkAdapter(ABC):
    type_name: str

    @abstractmethod
    async def run(self, context: AdapterContext) -> AdapterResult:
        raise NotImplementedError


def _summary(values: Any, unit: str) -> MetricSummary:
    if isinstance(values, dict):
        if "samples" in values:
            values = values["samples"]
        elif "value" in values:
            values = [values["value"]]
    elif isinstance(values, (int, float)):
        values = [values]
    if not isinstance(values, list):
        raise ValueError(f"metric must be a number, list, or object with samples/value; got {type(values).__name__}")
    return MetricSummary.from_values((float(value) for value in values), unit)


class LlamaCppAdapter(BenchmarkAdapter):
    type_name = "llama_cpp"

    async def run(self, context: AdapterContext) -> AdapterResult:
        profile = context.profile
        adapter = profile["adapter"]
        workload = profile["workload"]
        model = profile["model"]
        binary = str(adapter.get("binary", "llama-bench"))
        model_path = str(model["path"])
        runs = int(workload.get("runs", 5))
        prompt_tokens = int(workload.get("prompt_tokens", 512))
        generated_tokens = int(workload.get("generated_tokens", 128))
        context_depth = int(workload.get("context_depth_tokens", 0))
        extra_args = [str(value) for value in adapter.get("extra_args", [])]

        base = [binary, "-m", model_path, "-r", str(runs), "-o", "json", *extra_args]
        prefill_argv = [*base, "-p", str(prompt_tokens), "-n", "0"]
        decode_argv = [*base, "-p", "0", "-n", str(generated_tokens)]
        if context_depth > 0:
            decode_argv.extend(["-d", str(context_depth)])

        prefill_stdout, prefill_stderr, prefill_power = await context.execute("prefill", prefill_argv)
        decode_stdout, decode_stderr, decode_power = await context.execute("decode", decode_argv)

        prefill_json = json.loads(prefill_stdout.decode("utf-8"))
        decode_json = json.loads(decode_stdout.decode("utf-8"))
        if not isinstance(prefill_json, list) or not prefill_json:
            raise RuntimeError("llama-bench prefill output was not a non-empty JSON array")
        if not isinstance(decode_json, list) or not decode_json:
            raise RuntimeError("llama-bench decode output was not a non-empty JSON array")
        pp = next((row for row in prefill_json if int(row.get("n_prompt", 0)) > 0), prefill_json[0])
        tg = next((row for row in decode_json if int(row.get("n_gen", 0)) > 0), decode_json[0])

        pp_samples = pp.get("samples_ts") or [pp["avg_ts"]]
        tg_samples = tg.get("samples_ts") or [tg["avg_ts"]]
        result = AdapterResult(
            metrics={
                "prompt_tokens_per_second": MetricSummary.from_values(pp_samples, "tokens/s"),
                "generation_tokens_per_second": MetricSummary.from_values(tg_samples, "tokens/s"),
            },
            metadata={
                "runtime_name": "llama.cpp",
                "runtime_version": f"{pp.get('build_commit', 'unknown')}+{pp.get('build_number', 'unknown')}",
                "backend": pp.get("backends") or tg.get("backends") or adapter.get("backend", "unknown"),
                "cpu_info": pp.get("cpu_info"),
                "gpu_info": pp.get("gpu_info"),
                "model_type": pp.get("model_type"),
                "model_n_params": pp.get("model_n_params"),
                "n_gpu_layers": pp.get("n_gpu_layers"),
                "n_threads": pp.get("n_threads"),
            },
            fit_status="runtime_verified",
            raw={
                "prefill": prefill_json,
                "decode": decode_json,
                "stderr": {
                    "prefill": prefill_stderr.decode("utf-8", errors="replace"),
                    "decode": decode_stderr.decode("utf-8", errors="replace"),
                },
            },
        )
        if prefill_power is not None:
            result.power_windows["prefill"] = prefill_power
        if decode_power is not None:
            result.power_windows["decode"] = decode_power
        return result


class JsonCommandAdapter(BenchmarkAdapter):
    """Normalized bridge for vendor-native Hailo/SOPHGO/Tenstorrent/FPGA tools."""

    type_name = "json_command"
    runtime_family = "generic"

    def _format_argv(self, argv: list[Any], profile: dict[str, Any]) -> list[str]:
        model = profile["model"]
        workload = profile["workload"]
        values = {
            "model_path": model.get("path", ""),
            "model_name": model.get("name", ""),
            "prompt_tokens": workload.get("prompt_tokens", 0),
            "generated_tokens": workload.get("generated_tokens", 0),
            "context_tokens": workload.get("context_tokens", 0),
            "context_depth_tokens": workload.get("context_depth_tokens", 0),
            "runs": workload.get("runs", 1),
        }
        return [str(value).format_map(values) for value in argv]

    async def run(self, context: AdapterContext) -> AdapterResult:
        adapter = context.profile["adapter"]
        commands = adapter.get("commands")
        if commands is None:
            commands = {"active": adapter.get("command", [])}
        if not isinstance(commands, dict) or not commands:
            raise ValueError(f"{adapter.get('type')} adapter requires command or commands")

        merged_metrics: dict[str, MetricSummary] = {}
        metadata: dict[str, Any] = {
            "runtime_name": str(adapter.get("runtime_name", self.runtime_family)),
            "runtime_version": str(adapter.get("runtime_version", "unknown")),
            "backend": str(adapter.get("backend", self.runtime_family)),
        }
        fit_status = "unknown"
        raw: dict[str, Any] = {}
        windows: dict[str, PowerWindow] = {}

        for phase, raw_argv in commands.items():
            argv = self._format_argv(list(raw_argv), context.profile)
            stdout, stderr, window = await context.execute(str(phase), argv)
            payload = json.loads(stdout.decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError(f"{self.runtime_family} adapter output must be one JSON object")
            raw[str(phase)] = payload
            raw.setdefault("stderr", {})[str(phase)] = stderr.decode("utf-8", errors="replace")
            if window is not None:
                windows[str(phase)] = window
            fit_status = str(payload.get("fit_status", fit_status))
            metadata.update(payload.get("metadata", {}))
            for name, value in payload.get("metrics", {}).items():
                unit = "unknown"
                if isinstance(value, dict):
                    unit = str(value.get("unit", unit))
                merged_metrics[str(name)] = _summary(value, unit)

        if not merged_metrics:
            raise RuntimeError(f"{self.runtime_family} adapter produced no normalized metrics")
        return AdapterResult(
            metrics=merged_metrics,
            metadata=metadata,
            fit_status=fit_status,
            power_windows=windows,
            raw=raw,
        )


class HailoAdapter(JsonCommandAdapter):
    type_name = "hailo"
    runtime_family = "hailo"


class SophgoAdapter(JsonCommandAdapter):
    type_name = "sophgo"
    runtime_family = "sophgo-llm-tpu"


class TenstorrentAdapter(JsonCommandAdapter):
    type_name = "tenstorrent"
    runtime_family = "tt-metal"


class FpgaAdapter(JsonCommandAdapter):
    type_name = "fpga"
    runtime_family = "fpga-native"


_ADAPTERS: dict[str, type[BenchmarkAdapter]] = {
    LlamaCppAdapter.type_name: LlamaCppAdapter,
    "json_command": JsonCommandAdapter,
    HailoAdapter.type_name: HailoAdapter,
    SophgoAdapter.type_name: SophgoAdapter,
    TenstorrentAdapter.type_name: TenstorrentAdapter,
    FpgaAdapter.type_name: FpgaAdapter,
}


def adapter_names() -> list[str]:
    return sorted(_ADAPTERS)


def build_adapter(config: dict[str, Any]) -> BenchmarkAdapter:
    type_name = str(config.get("type", ""))
    try:
        return _ADAPTERS[type_name]()
    except KeyError as exc:
        raise ValueError(f"unsupported benchmark adapter {type_name!r}; choose from {', '.join(adapter_names())}") from exc
