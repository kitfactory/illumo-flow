"""Tracing utilities and adapters for illumo-flow."""

from __future__ import annotations

import contextvars
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Protocol, Sequence

from .tracing_db import SQLiteTracerDB, TempoTracerDB, TracerDB

class TracerProtocol(Protocol):
    """Minimal tracing protocol aligned with OpenAI Agents SDK."""

    def on_span_start(self, span: Mapping[str, Any]) -> None: ...

    def on_span_end(self, span: Mapping[str, Any]) -> None: ...

    def on_event(self, event: Mapping[str, Any]) -> None: ...


_CURRENT_TRACE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "illumo_flow_trace_id", default=None
)
_CURRENT_SPAN_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "illumo_flow_span_id", default=None
)
_CURRENT_TRACER: contextvars.ContextVar[Optional[TracerProtocol]] = contextvars.ContextVar(
    "illumo_flow_tracer", default=None
)


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class SpanTracker:
    """Manages span stack and context propagation for Flow execution."""

    def __init__(self, tracer: Optional[TracerProtocol], *, service_name: str = "illumo-flow") -> None:
        self._tracer = tracer
        self._service_name = service_name
        self._trace_id = uuid.uuid4().hex
        self._stack: list[tuple[str, contextvars.Token[Optional[str]]]] = []
        self._spans: Dict[str, Dict[str, Any]] = {}

        self._trace_token = _CURRENT_TRACE_ID.set(self._trace_id)
        self._tracer_token = _CURRENT_TRACER.set(tracer)

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def start_span(
        self,
        *,
        kind: str,
        name: str,
        attributes: Optional[Mapping[str, Any]] = None,
    ) -> str:
        span_id = uuid.uuid4().hex
        parent_span_id = self._stack[-1][0] if self._stack else None
        start_time = _utcnow()
        span_payload = {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "service_name": self._service_name,
            "kind": kind,
            "name": name,
            "attributes": dict(attributes or {}),
            "start_time": start_time,
        }
        self._spans[span_id] = span_payload

        if self._tracer is not None:
            try:
                self._tracer.on_span_start(span_payload)
            except Exception:
                pass

        span_token = _CURRENT_SPAN_ID.set(span_id)
        self._stack.append((span_id, span_token))
        return span_id

    def end_span(
        self,
        span_id: str,
        *,
        status: str = "OK",
        error: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
    ) -> None:
        span_token: Optional[contextvars.Token[Optional[str]]] = None
        while self._stack:
            current_id, token = self._stack.pop()
            _CURRENT_SPAN_ID.reset(token)
            if current_id == span_id:
                span_token = token
                break
        if span_token is None:
            return

        payload = self._spans.pop(span_id, {}).copy()
        payload.setdefault("trace_id", self._trace_id)
        payload.setdefault("span_id", span_id)
        payload["end_time"] = _utcnow()
        payload["status"] = status
        if error:
            payload["error"] = error
        if attributes:
            merged = payload.setdefault("attributes", {})
            merged.update(attributes)

        if self._tracer is not None:
            try:
                self._tracer.on_span_end(payload)
            except Exception:
                pass

        # restore parent span context if any
        if self._stack:
            _CURRENT_SPAN_ID.set(self._stack[-1][0])

    def emit_event(
        self,
        *,
        event_type: str,
        level: str = "info",
        message: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
        span_id: Optional[str] = None,
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return

        active_span_id = span_id or _CURRENT_SPAN_ID.get(None)
        if active_span_id is None:
            return

        event: Dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": active_span_id,
            "timestamp": _utcnow(),
            "event_type": event_type,
            "level": level,
        }
        if message is not None:
            event["message"] = message
        if attributes:
            event["attributes"] = dict(attributes)

        try:
            tracer.on_event(event)
        except Exception:
            pass

    def close(self) -> None:
        while self._stack:
            span_id, token = self._stack.pop()
            _CURRENT_SPAN_ID.reset(token)
            payload = self._spans.pop(span_id, None)
            if payload and self._tracer is not None:
                payload = payload.copy()
                payload["end_time"] = _utcnow()
                payload["status"] = payload.get("status", "OK")
                try:
                    self._tracer.on_span_end(payload)
                except Exception:
                    pass

        _CURRENT_TRACE_ID.reset(self._trace_token)
        _CURRENT_TRACER.reset(self._tracer_token)


def emit_event(
    event_type: str,
    *,
    level: str = "info",
    message: Optional[str] = None,
    attributes: Optional[Mapping[str, Any]] = None,
) -> None:
    tracer = _CURRENT_TRACER.get(None)
    trace_id = _CURRENT_TRACE_ID.get(None)
    span_id = _CURRENT_SPAN_ID.get(None)
    if tracer is None or trace_id is None or span_id is None:
        return

    event: Dict[str, Any] = {
        "trace_id": trace_id,
        "span_id": span_id,
        "timestamp": _utcnow(),
        "event_type": event_type,
        "level": level,
    }
    if message is not None:
        event["message"] = message
    if attributes:
        event["attributes"] = dict(attributes)

    try:
        tracer.on_event(event)
    except Exception:
        pass


class ConsoleTracer:
    """Tracer implementation that streams span information to the console."""

    _COLORS = {
        "flow": "\033[95m",
        "node": "\033[94m",
        "event": "\033[90m",
        "instruction": "\033[93m",
        "input": "\033[96m",
        "response": "\033[92m",
        "error": "\033[91m",
    }
    _RESET = "\033[0m"

    def __init__(
        self,
        *,
        stream: Optional[Any] = None,
        enable_color: Optional[bool] = None,
    ) -> None:
        self._stream = stream or sys.stdout
        if enable_color is None:
            enable_color = bool(hasattr(self._stream, "isatty") and self._stream.isatty())
        self._enable_color = enable_color
        self._depths: Dict[str, int] = {}

    def on_span_start(self, span: Mapping[str, Any]) -> None:
        parent = span.get("parent_span_id")
        depth = self._depths.get(parent, -1) + 1
        self._depths[span["span_id"]] = depth
        kind = span.get("kind", "event")
        name = span.get("name", "")
        msg = f"[{kind.upper()}] start name={name}"
        self._write(kind, msg, depth)

    def on_span_end(self, span: Mapping[str, Any]) -> None:
        span_id = span.get("span_id")
        depth = self._depths.pop(span_id, 0)
        kind = span.get("kind", "event")
        status = span.get("status", "OK")
        message = f"[{kind.upper()}] end status={status}"
        if span.get("error"):
            message += f" error={span['error']}"
        self._write(kind, message, depth)

    def on_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("event_type", "event")
        level = event.get("level", "info")
        message = event.get("message", "")
        attributes = event.get("attributes") or {}
        depth = self._depths.get(event.get("span_id"), 1)
        if attributes:
            attr_text = " ".join(f"{k}={v}" for k, v in attributes.items())
            if message:
                message = f"{message} {attr_text}"
            else:
                message = attr_text
        label = event_type.replace("agent_", "agent:")
        text = f"[{label}] {message}" if message else f"[{label}]"
        color_key = "error" if level.lower() == "error" else event_type
        self._write(color_key, text, depth)

    def _write(self, color_key: str, message: str, depth: int) -> None:
        indent = "  " * max(depth, 0)
        if self._enable_color and color_key in self._COLORS:
            payload = f"{self._COLORS[color_key]}{message}{self._RESET}"
        else:
            payload = message
        try:
            self._stream.write(f"{indent}{payload}\n")
            if hasattr(self._stream, "flush"):
                self._stream.flush()
        except Exception:
            pass


class SQLiteTracer:
    """Tracer that persists spans and events via a TracerDB backend."""

    def __init__(
        self,
        *,
        db_path: str | Path = "illumo_trace.db",
        db: Optional[TracerDB] = None,
    ) -> None:
        self._db: TracerDB = db or SQLiteTracerDB(db_path=db_path)
        self._db.connect()

    def on_span_start(self, span: Mapping[str, Any]) -> None:
        self._db.record_span(span)

    def on_span_end(self, span: Mapping[str, Any]) -> None:
        self._db.record_span(span)

    def on_event(self, event: Mapping[str, Any]) -> None:
        self._db.record_event(event)

    def close(self) -> None:
        self._db.close()


class OtelTracer:
    """Tracer that forwards spans and events through a TracerDB backend."""

    def __init__(
        self,
        *,
        service_name: str = "illumo-flow",
        exporter: Optional[Any] = None,
        db: Optional[TracerDB] = None,
    ) -> None:
        self._service_name = service_name
        self._db: TracerDB = db or TempoTracerDB(exporter=exporter)
        self._db.connect()

    def on_span_start(self, span: Mapping[str, Any]) -> None:
        payload = dict(span)
        payload.setdefault("service_name", self._service_name)
        self._db.record_span(payload)

    def on_span_end(self, span: Mapping[str, Any]) -> None:
        payload = dict(span)
        payload.setdefault("service_name", self._service_name)
        self._db.record_span(payload)
        self._db.flush()

    def on_event(self, event: Mapping[str, Any]) -> None:
        self._db.record_event(event)

    def close(self) -> None:
        self._db.close()


__all__ = [
    "TracerProtocol",
    "SpanTracker",
    "ConsoleTracer",
    "SQLiteTracer",
    "OtelTracer",
    "emit_event",
]
