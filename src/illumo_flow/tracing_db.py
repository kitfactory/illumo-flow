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
    policy_snapshot: dict[str, Any]
    timeout: bool


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


@dataclass
class TraceSummary:
    trace_id: str
    root_service: Optional[str]
    root_name: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    span_count: int


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

    def summaries(self, limit: Optional[int] = None) -> List[TraceSummary]:
        query = (
            "SELECT trace_id, "
            "MAX(CASE WHEN parent_span_id IS NULL THEN service_name END) AS root_service, "
            "MAX(CASE WHEN parent_span_id IS NULL THEN name END) AS root_name, "
            "MIN(start_time) AS start_time, "
            "MAX(end_time) AS end_time, "
            "COUNT(*) AS span_count "
            "FROM spans GROUP BY trace_id ORDER BY MIN(start_time) DESC"
        )
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()

        return [
            TraceSummary(
                trace_id=row[0],
                root_service=row[1],
                root_name=row[2],
                start_time=row[3],
                end_time=row[4],
                span_count=int(row[5] or 0),
            )
            for row in rows
        ]

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
        query = (
            "SELECT span_id, trace_id, parent_span_id, service_name, kind, name, attributes, "
            "status, error, start_time, end_time, policy_snapshot, timeout FROM spans"
        )
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
            legacy = False
            try:
                cur.execute(query, params)
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                legacy_query = (
                    "SELECT span_id, trace_id, parent_span_id, service_name, kind, name, attributes, "
                    "status, error, start_time, end_time FROM spans"
                )
                cur.execute(legacy_query, params)
                rows = cur.fetchall()
                legacy = True

        records: List[SpanRecord] = []
        for row in rows:
            if legacy:
                attributes = self._parse_literal(row[6])
                records.append(
                    SpanRecord(
                        span_id=row[0],
                        trace_id=row[1],
                        parent_span_id=row[2],
                        service_name=row[3],
                        kind=row[4],
                        name=row[5],
                        attributes=attributes,
                        status=row[7],
                        error=row[8],
                        start_time=row[9],
                        end_time=row[10],
                        policy_snapshot={},
                        timeout=False,
                    )
                )
            else:
                records.append(
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
                        policy_snapshot=self._parse_literal(row[11]),
                        timeout=bool(row[12]),
                    )
                )
        return records

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


__all__ = ["SQLiteTraceReader", "SpanRecord", "EventRecord", "TraceSummary"]
