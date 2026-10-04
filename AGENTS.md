# Observability Lab Project Guidance

## Goal

This repository is a learning lab for comparing OpenTelemetry auto-instrumentation with explicit SDK instrumentation. The application is a Flask checkout flow backed by PostgreSQL and consists of gateway, orders, and inventory services.

## Structure

- Keep the two complete implementations separate under `implementations/auto/` and `implementations/sdk/`.
- Keep each service independently buildable with its own Dockerfile and dependency file.
- Shared local infrastructure belongs in the root Compose file and `observability/` configuration.
- Helm deploys the selected application implementation and PostgreSQL. Its OTLP destination is configurable and may be an externally managed Collector.

## Behavior Contracts

- Keep routes, payloads, status codes, and database schema behavior equivalent between implementations.
- Preserve inventory's atomic conditional update so concurrent reservations cannot make stock negative.
- Keep service names, resource attributes, and OTLP endpoints configurable through environment variables.
- Avoid high-cardinality metric labels such as order IDs; use traces and logs for per-request detail.

## Instrumentation Boundary

- `auto/` must use the `opentelemetry-instrument` launcher and supported auto-instrumentation packages. Do not initialize SDK providers in application code there.
- `sdk/` must initialize its OpenTelemetry providers/exporters in application code and create its intended spans and metrics explicitly. Do not enable overlapping auto-instrumentors in that variant.
- Keep business logic independent of instrumentation so both versions remain behaviorally comparable.

## Verification

- Run `docker compose config` and Python syntax/tests after changes.
- Exercise health checks, successful checkout and order lookup, and insufficient-stock behavior in both modes.
- Inspect traces, metrics, and logs through the local Grafana stack.
- Run `helm lint` and render templates for both instrumentation modes.
- Document commands and configuration whenever the Compose or Helm interface changes.