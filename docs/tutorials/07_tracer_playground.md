# 7. Tracer Playground – See the Story

## Goal
Visualize what your flow is doing by switching between console, SQLite, and OTEL tracers.

## Why it’s satisfying
- You watch spans start/end for every node (instant debugging).
- SQLite gives you a permanent journal; OTEL lets you integrate with observability stacks.

## Steps
1. **ConsoleTracer (default)**
   ```python
   from illumo_flow import FlowRuntime, ConsoleTracer
   FlowRuntime.configure(tracer=ConsoleTracer())
   ```
   Run the multi-agent flow and note `[FLOW]` / `[NODE]` lines.

2. **SQLiteTracer**
   ```python
   from illumo_flow import SQLiteTracer
   FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))
   ```
   After running the flow, inspect the DB:
   ```python
   import sqlite3
   with sqlite3.connect("trace.db") as conn:
       for row in conn.execute("SELECT name, status, start_time FROM spans"):
           print(row)
   ```

3. **OtelTracer**
   ```python
   from illumo_flow import OtelTracer
   FlowRuntime.configure(tracer=OtelTracer(service_name="illumo-flow", exporter=my_exporter))
   ```
   Implement `my_exporter.export(spans)` to forward data to Jaeger/Tempo/etc.

4. **CLI switching**
   ```bash
   illumo run flow_launch.yaml --tracer sqlite --tracer-arg db_path=./trace.db
   illumo run flow_launch.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317
   ```

## Checklist
- [ ] Console logs are readable (`[FLOW]`, `[NODE]`, `[routing.enqueue]` etc.).
- [ ] SQLite DB contains span rows for flow/node.
- [ ] OTEL exporter receives span payloads (inspect your backend).

Tracer mastery makes production debugging a breeze. Next, we’ll tame fail-fast and retries with Policy in Chapter 8.
