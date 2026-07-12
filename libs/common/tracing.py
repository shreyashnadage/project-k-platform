"""OpenTelemetry tracing setup for the OCEN platform.

Configures OTLP export to SigNoz (or any OTel-compatible collector).
Toggle via OTEL_ENABLED=true. Exports to OTEL_EXPORTER_OTLP_ENDPOINT.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger()

OTEL_ENABLED = os.environ.get("OTEL_ENABLED", "false").lower() == "true"
OTEL_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "ocen-platform")
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def init_tracing(service_name: str | None = None) -> None:
    """Initialize OpenTelemetry tracing if enabled.

    Call once at service startup (worker.py, app.py).
    No-op if OTEL_ENABLED is not true — zero overhead in dev.
    """
    if not OTEL_ENABLED:
        logger.debug("otel_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name or OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        logger.info("otel_initialized", service=service_name, endpoint=OTEL_ENDPOINT)
    except ImportError:
        logger.warning("otel_packages_not_installed")


def get_tracer(name: str = "ocen"):
    """Get a tracer instance. Returns a no-op tracer if OTel is disabled."""
    if not OTEL_ENABLED:
        from opentelemetry import trace

        return trace.get_tracer(name)

    from opentelemetry import trace

    return trace.get_tracer(name)
