from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from class_os_contracts import RuntimeRequest


class SafeTelemetry:
    """Spike-only OTel sink with an explicit attribute allowlist."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("class-os.agent-boundary-spike")

    def record(self, request: RuntimeRequest, outcome: str, tool_names: tuple[str, ...]) -> None:
        with self.tracer.start_as_current_span("agent.run") as span:
            span.set_attribute("class_os.run_id", request.run_id)
            span.set_attribute("class_os.route_mode", request.route_mode.value)
            span.set_attribute("class_os.outcome", outcome)
            span.set_attribute("class_os.tool_count", len(tool_names))

    def attributes(self) -> list[dict[str, object]]:
        return [dict(span.attributes or {}) for span in self.exporter.get_finished_spans()]
