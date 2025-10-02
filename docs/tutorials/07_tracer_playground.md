# 7. Tracer Playground – See the Story

## You want to…
Observe every flow/node span and log without sprinkling print statements.

### Use tracers because…
- `ConsoleTracer`, `SQLiteTracer`, and `OtelTracer` all implement `TracerProtocol`, so switching them is frictionless.
- `SpanTracker` already emits flow/node span events—your job is just to choose the destination.
- ConsoleTracer colorizes Agent `instruction` / `input` / `response`, so you can read conversations at a glance.

## How to do it
1. Pick a tracer in `FlowRuntime.configure`.
2. Run your flow (e.g., the mini app from Chapter 6).
3. Inspect console output / SQLite DB / OTEL export.

```python
from illumo_flow import FlowRuntime, ConsoleTracer, SQLiteTracer, OtelTracer
from illumo_flow.tracing_db import TempoTracerDB

# Console: instruction/input/response are colorized for quick scanning
FlowRuntime.configure(tracer=ConsoleTracer())

# SQLite
FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))

# OTEL
FlowRuntime.configure(
    tracer=OtelTracer(
        service_name="illumo-flow",
        db=TempoTracerDB(exporter=my_exporter),
    )
)
```

CLI switches too:
```bash
illumo run flow_launch.yaml --tracer sqlite --tracer-arg db_path=./trace.db
illumo run flow_launch.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317
```

## Tracer insights
- ConsoleTracer prints `[FLOW]` spans in bright white and `[NODE]` spans in cyan; Agent instruction/input/response segments use yellow/blue/green respectively.
- SQLiteTracer now delegates to `SQLiteTracerDB`, so spans/events live in `spans` / `events` tables—great for building SQL dashboards.
- OtelTracer can be backed by `TempoTracerDB(exporter=...)` to reuse the OTLP exporter you already have in production.
- All tracers receive the same payload, so switching them never changes business logic—only the destination of telemetry.

### Sample output
ConsoleTracer during the coding assistant flow:

```
[FLOW] start name=inspect
  [NODE] start name=inspect
  [NODE] end status=OK
  [NODE] start name=apply_patch
  [NODE] end status=OK
  [NODE] start name=run_tests
  [NODE] end status=OK
  [NODE] start name=summarize
  [NODE] end status=OK
[FLOW] end status=OK
```

SQLiteTracer stores the same run in `trace.db`:

```sql
sqlite> SELECT kind, name, status FROM spans ORDER BY start_time LIMIT 3;
flow|inspect|OK
node|inspect|OK
node|apply_patch|OK
```

## Experiments
- Run the Chapter 6 flow with ConsoleTracer first, then swap to SQLiteTracer and compare how retries and router decisions appear in the database.
- Create a custom tracer that wraps ConsoleTracer but filters spans by `kind="node"` to spotlight only Agent interactions.
- Feed OTEL data into a dashboard and add alerts when EvaluationAgent spans exceed a latency threshold—useful for production monitoring.

## Learned in this chapter
- Tracers are pluggable via `FlowRuntime.configure(tracer=...)`.
- ConsoleTracer highlights Agent instruction/input/response while SQLite stores history and OTEL forwards spans.
- With observability handled, Chapter 8 focuses on error handling via Policy.
