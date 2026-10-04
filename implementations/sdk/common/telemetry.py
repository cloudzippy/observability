import logging
import os

from flask import g, request
from opentelemetry import context, metrics, propagate, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import OTELResourceDetector, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode


def configure_telemetry(app, service_name):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "observability-lab",
            "deployment.environment.name": os.getenv("ENVIRONMENT", "local"),
        }
    ).merge(OTELResourceDetector().detect())

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000")),
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"))
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

    tracer = tracer_provider.get_tracer(service_name)

    @app.before_request
    def start_server_span():
        parent_context = propagate.extract(request.headers)
        route = request.url_rule.rule if request.url_rule else request.path
        span = tracer.start_span(
            f"{request.method} {route}",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": request.method,
                "url.path": route,
                "service.name": service_name,
            },
        )
        g.otel_span = span
        g.otel_context_token = context.attach(trace.set_span_in_context(span, parent_context))

    @app.after_request
    def finish_server_span(response):
        span = getattr(g, "otel_span", None)
        if span is not None:
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            span.end()
            context.detach(g.otel_context_token)
        return response

    return tracer, metrics.get_meter(service_name)


def traced_post(tracer, url, payload):
    import requests

    with tracer.start_as_current_span("HTTP POST", kind=SpanKind.CLIENT) as span:
        span.set_attribute("http.request.method", "POST")
        span.set_attribute("server.address", url.split("/")[2].split(":")[0])
        headers = {}
        propagate.inject(headers)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=3)
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            return response
        except requests.RequestException as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def traced_execute(tracer, connection, statement, parameters=None):
    operation = statement.lstrip().split(None, 1)[0].upper()
    with tracer.start_as_current_span("postgresql.query", kind=SpanKind.CLIENT) as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", operation)
        try:
            return connection.execute(statement, parameters or ())
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
