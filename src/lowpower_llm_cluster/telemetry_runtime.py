from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping


@dataclass(slots=True)
class OtelRuntime:
    """Optional OTLP telemetry bridge; Prometheus remains dependency-light default."""

    endpoint: str | None = None
    service_name: str = "lowpower-llm-cluster"
    _tracer: Any = None
    _meter: Any = None
    _provider: Any = None
    _meter_provider: Any = None

    def start(self) -> None:
        if not self.endpoint:
            return
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise RuntimeError("OTLP requested but telemetry extras are not installed; install lowpower-llm-cluster[telemetry]") from exc
        resource = Resource.create({"service.name": self.service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=self.endpoint.rstrip("/") + "/v1/traces")))
        trace.set_tracer_provider(provider)
        reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=self.endpoint.rstrip("/") + "/v1/metrics"))
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        self._provider = provider
        self._meter_provider = meter_provider
        self._tracer = trace.get_tracer(self.service_name)
        self._meter = metrics.get_meter(self.service_name)

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.shutdown()
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
        self._provider = self._meter_provider = self._tracer = self._meter = None

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
        if self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name, attributes=dict(attributes or {})) as span:
            yield span

    def counter_add(self, name: str, value: int | float, attributes: Mapping[str, Any] | None = None) -> None:
        if self._meter is None:
            return
        counter = self._meter.create_counter(name)
        counter.add(value, dict(attributes or {}))
