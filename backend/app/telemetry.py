"""OpenTelemetry bootstrap (Sprint 7, closes D-3).

Wires up the tracer + meter providers, registers auto-instrumentation for
FastAPI, SQLAlchemy (async + sync engines), httpx, and Celery, and
exports both signals over OTLP/gRPC to whichever endpoint
`AEGIS_OTEL_ENDPOINT` points at (`otel-collector:4317` in compose).

Design notes:

- One module owns the entire setup so an operator chasing "where do
  traces come from" has exactly one file to read.
- Everything is no-op when `AEGIS_OTEL_ENABLED=false`. Local dev or a
  detached test run can opt out — important for the test suite, where
  instrumenting the FastAPI app twice (once per test setup) would error.
- Auto-instrumentation is idempotent here: each `Instrumentor.instrument()`
  call guards against double-registration via the library's own state,
  but we additionally short-circuit with `_installed = True`.
- Endpoint defaults to insecure gRPC because the collector lives on the
  same Docker network. Production deployments override via env.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.logging import get_logger

log = get_logger("telemetry")

_installed: bool = False


def configure_telemetry(app: Any | None) -> None:
    """Initialise OTel providers + register auto-instrumentation.

    Pass the FastAPI app for the web process; pass `None` from Celery
    worker process init (no HTTP server to instrument). Idempotent.
    """
    global _installed
    if _installed:
        return
    if not settings.otel_enabled:
        log.info("telemetry.disabled", reason="AEGIS_OTEL_ENABLED=false")
        _installed = True
        return

    # Lazy imports so test code that disables OTel doesn't even need the
    # libraries on PYTHONPATH.
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from app import __version__
    from app.db import engine

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": __version__,
            "deployment.environment": settings.env,
        }
    )

    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True))
    )
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=settings.otel_endpoint, insecure=True),
        export_interval_millis=10_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/v1/health,/api/v1/ready")
    # SQLAlchemy instrumentation works against the sync underlying engine
    # of an AsyncEngine via `engine.sync_engine`.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    HTTPXClientInstrumentor().instrument()
    CeleryInstrumentor().instrument()

    log.info(
        "telemetry.configured",
        endpoint=settings.otel_endpoint,
        service_name=settings.otel_service_name,
    )
    _installed = True
