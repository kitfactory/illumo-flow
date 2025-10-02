from __future__ import annotations

import sqlite3
from pathlib import Path

from illumo_flow.core import FlowError
from illumo_flow.tracing import OtelTracer, SQLiteTracer, SpanTracker, emit_event


class FakeExporter:
    def __init__(self) -> None:
        self.exported: list[list[dict[str, object]]] = []

    def export(self, spans: list[dict[str, object]]) -> None:
        self.exported.append(spans)


def test_sqlite_tracer_db_persists_span_and_event(tmp_path: Path) -> None:
    db_path = tmp_path / "trace.db"
    tracer = SQLiteTracer(db_path=db_path)
    tracker = SpanTracker(tracer=tracer, service_name="test-service")

    span_id = tracker.start_span(kind="flow", name="main")
    emit_event("node.start", message="begin", attributes={"node_id": "inspect"})
    tracker.end_span(span_id, status="OK")
    tracker.close()
    tracer.close()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name, status FROM spans")
    row = cur.fetchone()
    assert row == ("main", "OK")

    cur.execute("SELECT event_type, message FROM events")
    event_row = cur.fetchone()
    assert event_row == ("node.start", "begin")
    conn.close()


def test_tempo_tracer_db_exports_spans() -> None:
    exporter = FakeExporter()
    tracer = OtelTracer(service_name="demo", exporter=exporter)
    tracker = SpanTracker(tracer=tracer, service_name="demo")

    span_id = tracker.start_span(kind="flow", name="demo-flow")
    emit_event("node.start", attributes={"node_id": "inspect"})
    tracker.end_span(span_id, status="OK")
    tracker.close()
    tracer.close()

    assert exporter.exported, "Exporter should receive at least one batch"
    batch = exporter.exported[0]
    assert batch[0]["name"] == "demo-flow"
    assert batch[0]["service_name"] == "demo"
    assert batch[0]["events"]
