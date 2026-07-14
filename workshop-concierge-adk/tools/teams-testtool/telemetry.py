"""Console OpenTelemetry wiring for the LOCAL agent-mode host (test-only).

The production Foundry Hosted Agent runtime configures its own span exporter; when
you run the ADK agent locally there is **no** exporter, so the spans ``agent.py`` emits
(``workshop.tool.name`` / ``workshop.recommended_track`` / ``workshop.correlation_id``)
and the spans ADK/LiteLLM create would go nowhere. This module installs a global
:class:`TracerProvider` with a :class:`ConsoleSpanExporter` so every span prints to the
bot terminal — letting you *see* the real agent orchestrating a response.

Idempotent: calling :func:`setup_console_tracing` more than once is a no-op after the
first successful install.
"""
from __future__ import annotations

import os

_INSTALLED = False


def setup_console_tracing(service_name: str = "workshop-concierge-testtool") -> None:
    """Install a process-global console span exporter (once).

    Honors ``OTEL_SERVICE_NAME`` when set. Safe to call from any mode; it only does
    work in agent mode where the caller invokes it explicitly.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    resource = Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", service_name)}
    )
    provider = TracerProvider(resource=resource)

    # SimpleSpanProcessor flushes each span as it ends → immediate, ordered console
    # output that reads like a live trace during a turn. Set WC_OTEL_BATCH=1 to batch.
    exporter = ConsoleSpanExporter()
    if os.environ.get("WC_OTEL_BATCH") == "1":
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _INSTALLED = True


def get_tracer(name: str = "teams-testtool"):
    """Return a tracer from the (possibly console-wired) global provider."""
    from opentelemetry import trace

    return trace.get_tracer(name)
