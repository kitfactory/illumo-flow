"""Utilities for querying recorded trace data."""

from __future__ import annotations

import ast
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional


@dataclass
class SpanRecord:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    service_name: Optional[str]
    kind: Optional[str]
    name: Optional[str]
    status: Optional[str]
    error: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    attributes: dict[str, Any]


@dataclass
class EventRecord:
    id: int
    trace_id: str
    span_id: str
    event_type: Optional[str]
    level: Optional[str]
    message: Optional[str]
    attributes: dict[str, Any]
    timestamp: Optional[str]


class SQLiteTraceReader:
    """Query spans and events stored by `SQLiteTracer`."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(f"Trace database not found: {path}")
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def trace_ids(self, limit: Optional[int] = None) -> List[str]:
        query = "SELECT DISTINCT trace_id FROM spans ORDER BY start_time DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query)
            return [row[0] for row in cur.fetchall() if row[0]]

    def spans(
        self,
        *,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SpanRecord]:
        query = "SELECT span_id, trace_id, parent_span_id, service_name, kind, name, attributes, status, error, start_time, end_time FROM spans"
        conditions: List[str] = []
        params: List[Any] = []
        if span_id:
            conditions.append("span_id = ?")
            params.append(span_id)
        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if name:
            conditions.append("name = ?")
            params.append(name)
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY start_time"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()

        return [
            SpanRecord(
                span_id=row[0],
                trace_id=row[1],
                parent_span_id=row[2],
                service_name=row[3],
                kind=row[4],
                name=row[5],
                attributes=self._parse_literal(row[6]),
                status=row[7],
                error=row[8],
                start_time=row[9],
                end_time=row[10],
            )
            for row in rows
        ]

    def events(
        self,
        *,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventRecord]:
        query = "SELECT id, trace_id, span_id, event_type, level, message, attributes, timestamp FROM events"
        conditions: List[str] = []
        params: List[Any] = []
        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if span_id:
            conditions.append("span_id = ?")
            params.append(span_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if level:
            conditions.append("level = ?")
            params.append(level)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()

        return [
            EventRecord(
                id=row[0],
                trace_id=row[1],
                span_id=row[2],
                event_type=row[3],
                level=row[4],
                message=row[5],
                attributes=self._parse_literal(row[6]),
                timestamp=row[7],
            )
            for row in rows
        ]

    @staticmethod
    def _parse_literal(value: Any) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"raw": value}


__all__ = ["SQLiteTraceReader", "SpanRecord", "EventRecord"]
