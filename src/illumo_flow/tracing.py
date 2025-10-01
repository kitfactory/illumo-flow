"""Tracing adapters for illumo-flow."""

from __future__ import annotations

import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _emit_tracer_event(tracer: Any, method: str, *args: Any, **kwargs: Any) -> None:
    callback = getattr(tracer, method, None) if tracer is not None else None
    if callable(callback):
        try:
            callback(*args, **kwargs)
        except Exception:
            # Tracer failures must never break flow execution/トレーサー障害はワークフローに影響させない
            pass


class ConsoleTracer:
    """Lightweight tracer that streams span events to the console."""

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

    def flow_start(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._write(self._format("flow", f"[Flow] start entry={flow.entry_id}", level=0))

    def flow_end(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._write(self._format("flow", f"[Flow] end entry={flow.entry_id}", level=0))

    def flow_error(self, *, flow: Any, error: BaseException) -> None:
        self._write(
            self._format(
                "error",
                f"[Flow] error entry={flow.entry_id} type={error.__class__.__name__} message={error}",
                level=0,
            )
        )

    def node_start(self, *, flow: Any, node_id: str, node: Any, payload: Any) -> None:
        node_type = node.__class__.__name__
        self._write(
            self._format("node", f"[Node] start id={node_id} type={node_type}", level=1)
        )

    def node_end(self, *, flow: Any, node_id: str, node: Any, result: Any) -> None:
        summary = self._summarize(result)
        self._write(
            self._format("node", f"[Node] end id={node_id} result={summary}", level=1)
        )

    def node_error(self, *, flow: Any, node_id: str, node: Any, error: BaseException) -> None:
        self._write(
            self._format(
                "error",
                (
                    f"[Node] error id={node_id} type={error.__class__.__name__} "
                    f"message={error}"
                ),
                level=1,
            )
        )

    def agent_instruction(self, *, node_id: str, text: str) -> None:
        self._write(
            self._format("instruction", f"[Agent:{node_id}] instruction: {text}", level=2)
        )

    def agent_input(self, *, node_id: str, text: str) -> None:
        self._write(self._format("input", f"[Agent:{node_id}] input: {text}", level=2))

    def agent_response(self, *, node_id: str, text: str) -> None:
        self._write(
            self._format("response", f"[Agent:{node_id}] response: {text}", level=2)
        )

    def _format(self, color_key: str, message: str, *, level: int) -> str:
        indent = "  " * max(level, 0)
        colored = message
        if self._enable_color and color_key in self._COLORS:
            colored = f"{self._COLORS[color_key]}{message}{self._RESET}"
        return f"{indent}{colored}"

    def _write(self, text: str) -> None:
        self._stream.write(f"{text}\n")
        if hasattr(self._stream, "flush"):
            try:
                self._stream.flush()
            except Exception:
                pass

    def _summarize(self, value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(value, Mapping):
            keys = ",".join(list(value.keys())[:3])
            return f"mapping({keys})"
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return f"sequence(len={len(value)})"
        return value.__class__.__name__


class SQLiteTracer:
    """Tracer that persists span events into a SQLite database."""

    def __init__(
        self,
        *,
        db_path: str | Path = "illumo_trace.db",
    ) -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._prepare_schema()

    def flow_start(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._record("flow_start", None, f"entry={flow.entry_id}", level=0)

    def flow_end(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._record("flow_end", None, f"entry={flow.entry_id}", level=0)

    def flow_error(self, *, flow: Any, error: BaseException) -> None:
        self._record(
            "flow_error",
            None,
            f"entry={flow.entry_id} type={error.__class__.__name__} message={error}",
            level=0,
        )

    def node_start(self, *, flow: Any, node_id: str, node: Any, payload: Any) -> None:
        self._record("node_start", node_id, f"type={node.__class__.__name__}", level=1)

    def node_end(self, *, flow: Any, node_id: str, node: Any, result: Any) -> None:
        summary = ConsoleTracer()._summarize(result)
        self._record("node_end", node_id, f"result={summary}", level=1)

    def node_error(self, *, flow: Any, node_id: str, node: Any, error: BaseException) -> None:
        self._record(
            "node_error",
            node_id,
            f"type={error.__class__.__name__} message={error}",
            level=1,
        )

    def agent_instruction(self, *, node_id: str, text: str) -> None:
        self._record("agent_instruction", node_id, text, level=2)

    def agent_input(self, *, node_id: str, text: str) -> None:
        self._record("agent_input", node_id, text, level=2)

    def agent_response(self, *, node_id: str, text: str) -> None:
        self._record("agent_response", node_id, text, level=2)

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception:
            pass

    def _prepare_schema(self) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    node_id TEXT,
                    message TEXT,
                    level INTEGER NOT NULL
                )
                """
            )
            self._connection.commit()

    def _record(self, kind: str, node_id: Optional[str], message: str, *, level: int) -> None:
        timestamp = datetime.utcnow().isoformat()
        try:
            with self._lock:
                cursor = self._connection.cursor()
                cursor.execute(
                    "INSERT INTO spans (created_at, kind, node_id, message, level) VALUES (?, ?, ?, ?, ?)",
                    (timestamp, kind, node_id, message, level),
                )
                self._connection.commit()
        except Exception:
            pass

    def __del__(self) -> None:  # pragma: no cover
        try:
            self._connection.close()
        except Exception:
            pass


class OtelTracer:
    """Tracer that buffers span events and forwards them to an exporter."""

    def __init__(
        self,
        *,
        service_name: str = "illumo-flow",
        exporter: Optional[Any] = None,
    ) -> None:
        self.service_name = service_name
        self._exporter = exporter
        self._buffer: list[dict[str, Any]] = []

    def flow_start(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._record("flow_start", {"entry": flow.entry_id})

    def flow_end(self, *, flow: Any, context: Mapping[str, Any]) -> None:
        self._record("flow_end", {"entry": flow.entry_id})

    def flow_error(self, *, flow: Any, error: BaseException) -> None:
        self._record(
            "flow_error",
            {"entry": flow.entry_id, "exception": error.__class__.__name__, "message": str(error)},
        )

    def node_start(self, *, flow: Any, node_id: str, node: Any, payload: Any) -> None:
        self._record("node_start", {"node_id": node_id, "node_type": node.__class__.__name__})

    def node_end(self, *, flow: Any, node_id: str, node: Any, result: Any) -> None:
        summary = ConsoleTracer()._summarize(result)
        self._record("node_end", {"node_id": node_id, "result": summary})

    def node_error(self, *, flow: Any, node_id: str, node: Any, error: BaseException) -> None:
        self._record(
            "node_error",
            {"node_id": node_id, "exception": error.__class__.__name__, "message": str(error)},
        )

    def agent_instruction(self, *, node_id: str, text: str) -> None:
        self._record("agent_instruction", {"node_id": node_id, "text": text})

    def agent_input(self, *, node_id: str, text: str) -> None:
        self._record("agent_input", {"node_id": node_id, "text": text})

    def agent_response(self, *, node_id: str, text: str) -> None:
        self._record("agent_response", {"node_id": node_id, "text": text})

    def flush(self) -> None:
        self._export(self._buffer)

    def shutdown(self) -> None:
        self.flush()
        self._buffer.clear()

    def _record(self, kind: str, attributes: Mapping[str, Any]) -> None:
        event = {
            "service": self.service_name,
            "kind": kind,
            "attributes": dict(attributes),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._buffer.append(event)
        self._export([event])

    def _export(self, events: Sequence[Mapping[str, Any]]) -> None:
        if not events or self._exporter is None:
            return
        try:
            export = getattr(self._exporter, "export", None)
            if callable(export):
                export(list(events))
        except Exception:
            pass


__all__ = [
    "ConsoleTracer",
    "SQLiteTracer",
    "OtelTracer",
    "_emit_tracer_event",
]

