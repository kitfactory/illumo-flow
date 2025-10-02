"""Tracer database backends for persistence and exporting."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol


class TracerDB(Protocol):
    """Persistence contract used by tracer implementations."""

    def connect(self) -> None:
        """Initialise any resources needed by the backend."""

    def record_span(self, span: Mapping[str, Any]) -> None:
        """Persist span information (start/end updates are both delivered here)."""

    def record_event(self, event: Mapping[str, Any]) -> None:
        """Persist tracer events tied to spans."""

    def flush(self) -> None:
        """Flush in-memory buffers to the underlying store (if applicable)."""

    def close(self) -> None:
        """Release resources held by the backend."""


class SQLiteTracerDB:
    """SQLite-backed TracerDB implementation."""

    def __init__(self, *, db_path: str | Path = "illumo_trace.db") -> None:
        self._path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def connect(self) -> None:  # type: ignore[override]
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    parent_span_id TEXT,
                    service_name TEXT,
                    kind TEXT,
                    name TEXT,
                    attributes TEXT,
                    status TEXT,
                    error TEXT,
                    start_time TEXT,
                    end_time TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT,
                    span_id TEXT,
                    event_type TEXT,
                    level TEXT,
                    message TEXT,
                    attributes TEXT,
                    timestamp TEXT
                )
                """
            )
            self._conn.commit()

    def record_span(self, span: Mapping[str, Any]) -> None:  # type: ignore[override]
        if self._conn is None:
            raise RuntimeError("SQLiteTracerDB.connect() must be called before use")
        payload = dict(span)
        attributes = json.dumps(payload.get("attributes") or {}, ensure_ascii=False)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO spans (
                    span_id, trace_id, parent_span_id, service_name,
                    kind, name, attributes, status, error, start_time, end_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(span_id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    parent_span_id = excluded.parent_span_id,
                    service_name = excluded.service_name,
                    kind = excluded.kind,
                    name = excluded.name,
                    attributes = excluded.attributes,
                    status = COALESCE(excluded.status, spans.status),
                    error = COALESCE(excluded.error, spans.error),
                    start_time = COALESCE(spans.start_time, excluded.start_time),
                    end_time = COALESCE(excluded.end_time, spans.end_time)
                """,
                (
                    payload.get("span_id"),
                    payload.get("trace_id"),
                    payload.get("parent_span_id"),
                    payload.get("service_name"),
                    payload.get("kind"),
                    payload.get("name"),
                    attributes,
                    payload.get("status"),
                    payload.get("error"),
                    payload.get("start_time"),
                    payload.get("end_time"),
                ),
            )
            self._conn.commit()

    def record_event(self, event: Mapping[str, Any]) -> None:  # type: ignore[override]
        if self._conn is None:
            raise RuntimeError("SQLiteTracerDB.connect() must be called before use")
        payload = dict(event)
        attributes = json.dumps(payload.get("attributes") or {}, ensure_ascii=False)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO events (
                    trace_id, span_id, event_type, level, message, attributes, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("trace_id"),
                    payload.get("span_id"),
                    payload.get("event_type"),
                    payload.get("level"),
                    payload.get("message"),
                    attributes,
                    payload.get("timestamp"),
                ),
            )
            self._conn.commit()

    def flush(self) -> None:  # type: ignore[override]
        if self._conn is not None:
            with self._lock:
                self._conn.commit()

    def close(self) -> None:  # type: ignore[override]
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None


class TempoTracerDB:
    """TracerDB implementation that forwards spans to an OTLP exporter."""

    def __init__(self, *, exporter: Optional[Any] = None, max_batch_size: int = 50) -> None:
        self._exporter = exporter
        self._max_batch_size = max_batch_size
        self._spans: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:  # type: ignore[override]
        self._spans = {}

    def record_span(self, span: Mapping[str, Any]) -> None:  # type: ignore[override]
        payload = dict(span)
        span_id = str(payload.get("span_id"))
        if not span_id:
            return
        existing = self._spans.get(span_id, {})
        merged = {**existing, **payload}
        self._spans[span_id] = merged
        if len(self._spans) >= self._max_batch_size:
            self.flush()

    def record_event(self, event: Mapping[str, Any]) -> None:  # type: ignore[override]
        span_id = event.get("span_id")
        if span_id is None:
            return
        payload = self._spans.setdefault(str(span_id), {"span_id": span_id})
        payload.setdefault("events", []).append(dict(event))

    def flush(self) -> None:  # type: ignore[override]
        if not self._spans or self._exporter is None:
            return
        batch: Iterable[dict[str, Any]] = list(self._spans.values())
        self._spans = {}
        try:
            self._exporter.export(list(batch))
        except Exception:
            for item in batch:
                span_id = str(item.get("span_id"))
                if span_id:
                    self._spans[span_id] = item

    def close(self) -> None:  # type: ignore[override]
        self.flush()


__all__ = ["TracerDB", "SQLiteTracerDB", "TempoTracerDB"]
