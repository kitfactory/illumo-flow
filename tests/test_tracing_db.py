from __future__ import annotations

import io
from pathlib import Path

from illumo_flow.tracing import SQLiteTracer, SpanTracker, emit_event
from illumo_flow.tracing_db import EventRecord, SQLiteTraceReader
from illumo_flow.cli import main as cli_main


def create_trace(db_path: Path) -> str:
    tracer = SQLiteTracer(db_path=db_path)
    tracker = SpanTracker(tracer=tracer, service_name="test")
    span_id = tracker.start_span(
        kind="flow",
        name="demo-flow",
        attributes={"node_id": "inspect"},
    )
    emit_event("node.start", message="begin", attributes={"node_id": "inspect"})
    tracker.end_span(span_id, status="OK")
    tracker.close()
    tracer.close()
    return tracker.trace_id


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


def test_cli_trace_list_with_traceql(tmp_path: Path) -> None:
    db_path = tmp_path / "trace.db"
    trace_id = create_trace(db_path)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli_main(
        [
            "trace",
            "list",
            "--db",
            str(db_path),
            "--traceql",
            "traces{} | pick(trace_id, root_service, start_time) | limit 5",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert not stderr.getvalue()
    assert trace_id in output
    assert "root_service" in output


def test_cli_trace_search_by_attribute(tmp_path: Path) -> None:
    db_path = tmp_path / "trace.db"
    trace_id = create_trace(db_path)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli_main(
        [
            "trace",
            "search",
            "--db",
            str(db_path),
            "--traceql",
            'span.attributes["node_id"] == "inspect"',
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert not stderr.getvalue()
    assert trace_id in output
    assert "demo-flow" in output
