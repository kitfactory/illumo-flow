from __future__ import annotations

from pathlib import Path

from illumo_flow.tracing import SQLiteTracer, SpanTracker, emit_event
from illumo_flow.tracing_db import EventRecord, SQLiteTraceReader


def create_trace(db_path: Path) -> None:
    tracer = SQLiteTracer(db_path=db_path)
    tracker = SpanTracker(tracer=tracer, service_name="test")
    span_id = tracker.start_span(kind="flow", name="demo-flow")
    emit_event("node.start", message="begin", attributes={"node_id": "inspect"})
    tracker.end_span(span_id, status="OK")
    tracker.close()
    tracer.close()


def test_sqlite_trace_reader_lists_spans_and_events(tmp_path: Path) -> None:
    db_path = tmp_path / "trace.db"
    create_trace(db_path)

    reader = SQLiteTraceReader(db_path)

    spans = reader.spans()
    assert spans
    span = spans[0]
    assert span.name == "demo-flow"
    assert span.status == "OK"

    events = reader.events(span_id=span.span_id)
    assert events
    event = events[0]
    assert isinstance(event, EventRecord)
    assert event.event_type == "node.start"
    assert event.attributes.get("node_id") == "inspect"


def test_sqlite_trace_reader_filters_by_trace_id(tmp_path: Path) -> None:
    db_path = tmp_path / "trace.db"
    create_trace(db_path)

    reader = SQLiteTraceReader(db_path)
    trace_ids = reader.trace_ids()
    assert trace_ids

    filtered = reader.spans(trace_id=trace_ids[0])
    assert filtered
    assert filtered[0].trace_id == trace_ids[0]
