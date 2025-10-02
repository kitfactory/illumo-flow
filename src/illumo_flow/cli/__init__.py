"""illumo CLI entrypoint for flow execution and trace inspection./フロー実行とトレース調査のための illumo CLI エントリーポイント"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, TextIO

from illumo_flow import ConsoleTracer, Flow, FlowError, FlowRuntime, RuntimeExecutionReport
from illumo_flow.policy import Policy, PolicyValidationError, PolicyValidator
from illumo_flow.tracing import OtelTracer, SQLiteTracer
from illumo_flow.tracing_db import EventRecord, SQLiteTraceReader, SpanRecord, TraceSummary


@dataclass
class TraceQLFilters:
    """Container for simplified TraceQL filters./簡易 TraceQL フィルタのコンテナ"""

    trace_id: Optional[str] = None
    span_name: Optional[str] = None
    span_kind: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    limit: Optional[int] = None
    pick: List[str] = field(default_factory=list)


class CLIError(Exception):
    """Raised when CLI parameters are invalid./CLI パラメータが不正な場合に送出"""


def _read_source(value: Optional[str]) -> Optional[str]:
    """Load inline value, @file, or stdin payload./インライン・@ファイル・標準入力から値を取得"""

    if value is None:
        return None
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        target = value[1:]
        if target == "-":
            return sys.stdin.read()
        try:
            return Path(target).read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem errors/ファイルシステム例外
            raise CLIError(f"Unable to read file '{target}': {exc}") from exc
    return value


def _load_json_payload(value: Optional[str], *, default: Any) -> Any:
    """Parse JSON payload using supported sources./対応ソースから JSON ペイロードを解析"""

    text = _read_source(value)
    if text is None:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid JSON payload: {exc}") from exc


def _coerce_value(raw: str) -> Any:
    """Convert `--set` values into Python literals./--set の値を Python リテラルへ変換"""

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        lowered = raw.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered == "null":
            return None
        return raw


def _assign_path(context: MutableMapping[str, Any], path: str, value: Any) -> None:
    """Assign dotted path values into the context mapping./ドット区切りパスでコンテキストへ値を設定"""

    if not path:
        raise CLIError("Empty key for --set")
    parts = [segment for segment in path.split(".") if segment]
    if not parts:
        raise CLIError(f"Invalid key: {path}")
    current: MutableMapping[str, Any] = context
    for segment in parts[:-1]:
        nested = current.get(segment)
        if not isinstance(nested, MutableMapping):
            nested = {}
            current[segment] = nested
        current = nested
    current[parts[-1]] = value


def _apply_sets(context: MutableMapping[str, Any], overrides: Iterable[str]) -> None:
    """Apply `--set key=value` overrides onto the context./--set key=value で指定された上書きを反映"""

    for item in overrides:
        if "=" not in item:
            raise CLIError("--set requires KEY=VALUE format")
        key, raw_value = item.split("=", 1)
        _assign_path(context, key, _coerce_value(raw_value))


def _json_ready_context(context: MutableMapping[str, Any]) -> Dict[str, Any]:
    """Return JSON-safe copy without runtime objects./ランタイム情報を除いた JSON 対応コピーを返す"""

    safe: Dict[str, Any] = {}
    for key, value in context.items():
        if key == "runtime":
            continue
        safe[key] = value
    return safe


def _json_dumps(payload: Any, *, pretty: bool) -> str:
    """Serialize payload with optional indentation./必要に応じてインデント付きで JSON 化"""

    return json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False)


def _format_policy_snapshot(policy_snapshot: Mapping[str, Any]) -> str:
    """Render policy snapshot into a concise string./ポリシー情報を要約文字列へ整形"""

    if not policy_snapshot:
        return "-"
    retry = policy_snapshot.get("retry") or {}
    on_error = policy_snapshot.get("on_error") or {}
    parts = [
        f"fail_fast={policy_snapshot.get('fail_fast')}",
        f"timeout={policy_snapshot.get('timeout')}",
        (
            "retry="
            f"max_attempts={retry.get('max_attempts')}"
            f",delay={retry.get('delay')}"
            f",mode={retry.get('mode')}"
        ),
        f"on_error={on_error.get('action')}->{on_error.get('target')}" if on_error.get("action") == "goto" else f"on_error={on_error.get('action')}",
    ]
    return ", ".join(parts)


def _report_to_markdown(report: RuntimeExecutionReport) -> str:
    data = report.to_dict()
    policy_json = json.dumps(data.get("policy_snapshot", {}), indent=2, ensure_ascii=False)
    context_json = json.dumps(data.get("context_digest", {}), indent=2, ensure_ascii=False)
    lines = [
        "# illumo-flow Failure Report",
        "",
        f"- trace_id: {data.get('trace_id') or '-'}",
        f"- failed_node_id: {data.get('failed_node_id') or '-'}",
        f"- summary: {data.get('summary') or '-'}",
        "",
        "## Policy Snapshot",
        "```json",
        policy_json,
        "```",
        "",
        "## Context Digest",
        "```json",
        context_json,
        "```",
        "",
    ]
    return "\n".join(lines)


def _write_failure_report(
    report: RuntimeExecutionReport,
    *,
    path: Path,
    fmt: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "markdown":
        payload = _report_to_markdown(report)
    else:
        payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")


def _append_runtime_log(report: RuntimeExecutionReport, *, log_path: Path) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": report.trace_id,
        "failed_node_id": report.failed_node_id,
        "summary": report.summary,
        "policy_snapshot": report.policy_snapshot,
        "context_digest": report.context_digest,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _print_failure_summary(
    report: RuntimeExecutionReport,
    *,
    stderr: TextIO,
) -> None:
    stderr.write("Flow failed.\n")
    stderr.write(f"  trace_id: {report.trace_id or '-'}\n")
    stderr.write(f"  failed_node: {report.failed_node_id or '-'}\n")
    stderr.write(f"  reason: {report.summary or '-'}\n")
    stderr.write(f"  policy: {_format_policy_snapshot(report.policy_snapshot)}\n")
    digest = report.context_digest or {}
    payload_preview = digest.get("payload_preview")
    if payload_preview:
        stderr.write(f"  payload_preview: {payload_preview}\n")
    stderr.write("\n")


def _build_policy(override: Optional[str], base: Policy) -> Policy:
    """Merge JSON override into base policy./ベースポリシーへ JSON の上書きを適用"""

    try:
        normalized_base = PolicyValidator.normalize(base)
    except PolicyValidationError as exc:
        raise CLIError(f"Invalid base policy: {exc}") from exc

    if override is None:
        return normalized_base
    payload = _load_json_payload(override, default=None)
    if payload is None:
        return normalized_base
    if not isinstance(payload, dict):
        raise CLIError("Policy override must decode to a JSON object")
    try:
        return PolicyValidator.normalize(payload, base=normalized_base)
    except PolicyValidationError as exc:
        raise CLIError(f"Invalid policy override: {exc}") from exc


def _resolve_tracer(name: Optional[str], trace_db: Path, service_name: str) -> Optional[object]:
    """Instantiate tracer based on CLI option./CLI オプションからトレーサーを生成する"""

    if name is None:
        return None
    key = name.strip().lower()
    if key in {"console", "stdout"}:
        return ConsoleTracer()
    if key in {"sqlite", "db"}:
        trace_db.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteTracer(db_path=trace_db)
    if key == "otel":
        return OtelTracer(service_name=service_name)
    raise CLIError(f"Unknown tracer: {name}")


def _close_tracer(tracer: Optional[object]) -> None:
    """Close tracer if supported./対応していればトレーサーをクローズする"""

    if tracer is None:
        return
    close = getattr(tracer, "close", None)
    if callable(close):
        close()


TRACE_ID_PATTERN = re.compile(r"trace_id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
ATTR_PATTERN = re.compile(r"span\.attributes\[\"([^\"]+)\"\]\s*==\s*['\"]([^'\"]+)['\"]")
NAME_PATTERN = re.compile(r"span\.name\s*==\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
KIND_PATTERN = re.compile(r"span\.kind\s*==\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
LIMIT_PATTERN = re.compile(r"limit\s+(\d+)", re.IGNORECASE)
PICK_PATTERN = re.compile(r"pick\s*\(([^)]+)\)", re.IGNORECASE)


def _parse_traceql(query: Optional[str]) -> TraceQLFilters:
    """Extract limited filters from TraceQL-like syntax./TraceQL 風構文からフィルタ条件を抽出"""

    filters = TraceQLFilters()
    if not query:
        return filters
    segments = [segment.strip() for segment in query.split("|") if segment.strip()]
    for segment in segments:
        if segment.lower().startswith("traces"):
            continue
        limit_match = LIMIT_PATTERN.search(segment)
        if limit_match:
            filters.limit = int(limit_match.group(1))
        pick_match = PICK_PATTERN.search(segment)
        if pick_match:
            picks = [item.strip() for item in pick_match.group(1).split(",") if item.strip()]
            filters.pick = picks
            continue
        trace_match = TRACE_ID_PATTERN.search(segment)
        if trace_match:
            filters.trace_id = trace_match.group(1)
        name_match = NAME_PATTERN.search(segment)
        if name_match:
            filters.span_name = name_match.group(1)
        kind_match = KIND_PATTERN.search(segment)
        if kind_match:
            filters.span_kind = kind_match.group(1)
        attr_match = ATTR_PATTERN.search(segment)
        if attr_match:
            key, value = attr_match.groups()
            filters.attributes[key] = value
    return filters


def _render_table(columns: Sequence[str], rows: Sequence[Sequence[Any]], *, out: TextIO) -> None:
    """Render a lightweight text table./簡易テキストテーブルを描画"""

    if not rows:
        out.write("(no results)\n")
        return
    widths = [len(str(column)) for column in columns]
    normalized_rows: List[List[str]] = []
    for row in rows:
        rendered_row: List[str] = []
        for idx, value in enumerate(row):
            text = "-" if value in (None, "") else str(value)
            widths[idx] = max(widths[idx], len(text))
            rendered_row.append(text)
        normalized_rows.append(rendered_row)

    header = " | ".join(str(column).ljust(widths[idx]) for idx, column in enumerate(columns))
    out.write(header + "\n")
    out.write("-+-".join("-" * width for width in widths) + "\n")
    for row in normalized_rows:
        line = " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(columns)))
        out.write(line + "\n")


def _render_markdown(columns: Sequence[str], rows: Sequence[Sequence[Any]], *, out: TextIO) -> None:
    if not rows:
        out.write("| " + " | ".join(columns) + " |\n")
        out.write("| " + " | ".join("---" for _ in columns) + " |\n")
        return
    out.write("| " + " | ".join(columns) + " |\n")
    out.write("| " + " | ".join("---" for _ in columns) + " |\n")
    for row in rows:
        rendered = ["-" if value in (None, "") else str(value) for value in row]
        out.write("| " + " | ".join(rendered) + " |\n")


def _render_rows(
    fmt: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    out: TextIO,
) -> None:
    if fmt == "json":
        payload = [
            {column: row[idx] for idx, column in enumerate(columns)}
            for row in rows
        ]
        out.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    elif fmt == "markdown":
        _render_markdown(columns, rows, out=out)
    else:
        _render_table(columns, rows, out=out)


def _render_span_tree(
    spans: Sequence[SpanRecord],
    *,
    events: Dict[str, List[EventRecord]],
    include_events: bool,
    out: TextIO,
) -> None:
    by_id = {span.span_id: span for span in spans}
    children: Dict[Optional[str], List[SpanRecord]] = defaultdict(list)
    for span in spans:
        children[span.parent_span_id].append(span)

    visited: set[str] = set()

    def walk(span: SpanRecord, depth: int) -> None:
        if span.span_id in visited:
            return
        visited.add(span.span_id)
        status = span.status or "OK"
        timeout_marker = " timeout" if span.timeout else ""
        name = span.name or span.span_id
        out.write(f"{'  ' * depth}- {name} [{status}]{timeout_marker}\n")
        if include_events:
            for event in events.get(span.span_id, []):
                message = event.message or ""
                out.write(
                    f"{'  ' * (depth + 1)}* {event.event_type or 'event'}"
                    f" {message}\n"
                )
        for child in children.get(span.span_id, []):
            walk(child, depth + 1)

    roots = children.get(None, []) or [span for span in spans if span.parent_span_id not in by_id]
    for root in roots:
        walk(root, 0)


def _ensure_reader(db_path: Path, *, stderr: TextIO) -> Optional[SQLiteTraceReader]:
    """Instantiate SQLiteTraceReader with error handling./エラーハンドリング付きで SQLiteTraceReader を生成"""

    try:
        return SQLiteTraceReader(db_path)
    except FileNotFoundError as exc:
        stderr.write(f"{exc}\n")
        return None


def _filter_spans_by_attributes(spans: Iterable[SpanRecord], attributes: Dict[str, str]) -> List[SpanRecord]:
    """Filter spans by attribute equality./属性の等価条件で span を抽出"""

    if not attributes:
        return list(spans)
    matched: List[SpanRecord] = []
    for span in spans:
        values = span.attributes or {}
        if all(str(values.get(key)) == value for key, value in attributes.items()):
            matched.append(span)
    return matched


def handle_run(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """Execute the `run` command./`run` コマンドを実行"""

    try:
        flow = Flow.from_config(args.flow_path)
    except Exception as exc:
        stderr.write(f"Failed to load flow: {exc}\n")
        return 1

    try:
        context_data = _load_json_payload(args.context, default={})
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    if not isinstance(context_data, MutableMapping):
        stderr.write("Context must decode to an object/コンテキストは JSON オブジェクトである必要があります\n")
        return 1

    try:
        _apply_sets(context_data, args.set or [])
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    previous_runtime = FlowRuntime.current()
    previous_policy = previous_runtime.policy

    try:
        desired_tracer = _resolve_tracer(args.tracer, args.trace_db, args.service_name)
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    try:
        merged_policy = _build_policy(args.policy, PolicyValidator.normalize(previous_policy))
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    tracer_to_use = desired_tracer if desired_tracer is not None else previous_runtime.tracer
    FlowRuntime.configure(
        tracer=tracer_to_use,
        policy=merged_policy,
        llm_factory=previous_runtime.llm_factory,
    )

    report = RuntimeExecutionReport()
    failure_exc: Optional[Exception] = None
    try:
        result_context = flow.run(context=context_data, report=report)
    except (FlowError, Exception) as exc:
        failure_exc = exc
        result_context = None
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_policy,
            llm_factory=previous_runtime.llm_factory,
        )
        if args.tracer is not None:
            _close_tracer(desired_tracer)

    if failure_exc is not None:
        if report.summary is None:
            report.summary = str(failure_exc)
        if args.report_path is not None:
            try:
                _write_failure_report(report, path=args.report_path, fmt=args.report_format)
            except Exception as exc:  # pragma: no cover - filesystem/ファイル書き込み例外
                stderr.write(f"Failed to write report: {exc}\n")
        try:
            _append_runtime_log(report, log_path=args.log_dir / "runtime_execution.log")
        except Exception as exc:  # pragma: no cover - filesystem issues/ファイル書き込み例外
            stderr.write(f"Failed to append runtime log: {exc}\n")
        _print_failure_summary(report, stderr=stderr)
        return 1

    if args.report_path is not None and report.failed_node_id:
        try:
            _write_failure_report(report, path=args.report_path, fmt=args.report_format)
        except Exception as exc:  # pragma: no cover
            stderr.write(f"Failed to write report: {exc}\n")

    safe_result = _json_ready_context(result_context)
    payload_text = _json_dumps(safe_result, pretty=args.pretty)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload_text, encoding="utf-8")
    else:
        stdout.write(payload_text + "\n")
    return 0


def handle_trace_list(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """Execute `trace list`./`trace list` コマンドを実行"""

    filters = _parse_traceql(args.traceql)
    reader = _ensure_reader(args.db, stderr=stderr)
    if reader is None:
        return 1
    summaries = reader.summaries(limit=filters.limit)

    picks = filters.pick or ["trace_id", "root_service", "start_time"]
    rows: List[List[Any]] = []
    for summary in summaries:
        mapping = {
            "trace_id": summary.trace_id,
            "root_service": summary.root_service,
            "root_name": summary.root_name,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
            "span_count": summary.span_count,
        }
        rows.append([mapping.get(column) for column in picks])

    if not rows:
        if args.format == "json":
            stdout.write("[]\n")
        else:
            stdout.write("No traces found/トレースは見つかりませんでした\n")
        return 0

    _render_rows(args.format, picks, rows, out=stdout)
    return 0


def handle_trace_show(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """Execute `trace show`./`trace show` コマンドを実行"""

    filters = _parse_traceql(args.traceql)
    target_id = args.trace_id or filters.trace_id
    if not target_id:
        stderr.write("trace_id is required via argument or TraceQL/trace_id は引数または TraceQL で指定してください\n")
        return 1

    reader = _ensure_reader(args.db, stderr=stderr)
    if reader is None:
        return 1
    spans = reader.spans(trace_id=target_id)
    if not spans:
        stderr.write(f"Trace '{target_id}' not found/トレース '{target_id}' が見つかりません\n")
        return 1

    events_map: Dict[str, List[EventRecord]] = {}
    if args.include_events:
        for event in reader.events(trace_id=target_id):
            events_map.setdefault(event.span_id, []).append(event)

    if args.format == "json":
        payload = []
        for span in spans:
            record = {
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "name": span.name,
                "kind": span.kind,
                "status": span.status,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "attributes": span.attributes,
                "policy_snapshot": span.policy_snapshot,
                "timeout": span.timeout,
            }
            if args.include_events:
                record["events"] = [
                    {
                        "event_type": event.event_type,
                        "level": event.level,
                        "message": event.message,
                        "timestamp": event.timestamp,
                        "attributes": event.attributes,
                    }
                    for event in events_map.get(span.span_id, [])
                ]
            payload.append(record)
        stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.format == "tree":
        _render_span_tree(spans, events=events_map, include_events=args.include_events, out=stdout)
        return 0

    rows = [
        [
            span.span_id,
            span.parent_span_id,
            span.name,
            span.kind,
            span.status,
            span.timeout,
            span.start_time,
            span.end_time,
        ]
        for span in spans
    ]
    _render_rows(
        args.format,
        ["span_id", "parent", "name", "kind", "status", "timeout", "start_time", "end_time"],
        rows,
        out=stdout,
    )

    if not args.include_events:
        return 0

    if not events_map:
        stdout.write("No events recorded/イベントは記録されていません\n")
        return 0

    for span in spans:
        scoped = events_map.get(span.span_id)
        if not scoped:
            continue
        stdout.write(f"Events for span {span.span_id} ({span.name}):\n")
        event_rows = [
            [event.event_type, event.level, event.message, event.timestamp]
            for event in scoped
        ]
        _render_rows(
            "table" if args.format != "markdown" else "markdown",
            ["event_type", "level", "message", "timestamp"],
            event_rows,
            out=stdout,
        )
    return 0


def handle_trace_search(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """Execute `trace search`./`trace search` コマンドを実行"""

    filters = _parse_traceql(args.traceql)
    effective_limit = args.limit if args.limit is not None else filters.limit

    reader = _ensure_reader(args.db, stderr=stderr)
    if reader is None:
        return 1

    spans = reader.spans(
        trace_id=filters.trace_id,
        name=filters.span_name,
        kind=filters.span_kind,
    )
    filtered = _filter_spans_by_attributes(spans, filters.attributes)

    if args.status:
        filtered = [span for span in filtered if (span.status or "").upper() == args.status]
    if args.timeout_only:
        filtered = [span for span in filtered if span.timeout]

    if effective_limit is not None:
        filtered = filtered[: effective_limit]

    if not filtered:
        if args.format == "json":
            stdout.write("[]\n")
        else:
            stdout.write("No spans matched/一致する span はありませんでした\n")
        return 0

    if args.format == "json":
        payload = [
            {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "name": span.name,
                "kind": span.kind,
                "status": span.status,
                "timeout": span.timeout,
                "attributes": span.attributes,
                "policy_snapshot": span.policy_snapshot,
            }
            for span in filtered
        ]
        stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    rows = [
        [
            span.trace_id,
            span.span_id,
            span.name,
            span.kind,
            span.status,
            span.timeout,
        ]
        for span in filtered
    ]
    _render_rows(
        args.format,
        ["trace_id", "span_id", "name", "kind", "status", "timeout"],
        rows,
        out=stdout,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser./CLI 引数パーサーを構築"""

    parser = argparse.ArgumentParser(description="illumo flow CLI./illumo フロー CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Execute a flow configuration./フロー構成を実行")
    run_parser.add_argument("flow_path", type=Path, help="Flow YAML/JSON path./フローの YAML/JSON パス")
    run_parser.add_argument("--context", "-c", help="Inline JSON, @file, or '-' for stdin./インライン JSON・@ファイル・'-' (標準入力)")
    run_parser.add_argument("--tracer", help="Tracer backend (console/sqlite/otel)./トレーサー backend (console/sqlite/otel)")
    run_parser.add_argument("--trace-db", type=Path, default=Path("illumo_trace.db"), help="SQLite tracer output path./SQLite トレーサーの出力先")
    run_parser.add_argument("--policy", help="Policy override JSON or @file./Policy 上書き用 JSON もしくは @ファイル")
    run_parser.add_argument("--output", "-o", type=Path, help="Write resulting context JSON to file./実行結果コンテキストをファイルへ出力")
    run_parser.add_argument("--set", action="append", help="Override context fields (KEY=VALUE)./コンテキストフィールドを上書き (KEY=VALUE)")
    run_parser.add_argument("--service-name", default="illumo-flow", help="Service name for OTEL tracer./OTEL トレーサーのサービス名")
    run_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output./JSON を整形して出力")
    run_parser.add_argument("--report-path", type=Path, help="Write failure summary to file./失敗サマリをファイルへ出力")
    run_parser.add_argument(
        "--report-format",
        choices=("json", "markdown"),
        default="json",
        help="Failure report format (json/markdown)./失敗レポートの形式 (json/markdown)",
    )
    run_parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory for runtime_execution.log./runtime_execution.log の出力先ディレクトリ",
    )
    run_parser.set_defaults(func=handle_run)

    trace_parser = subparsers.add_parser("trace", help="Trace inspection commands./トレース調査コマンド")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command")

    list_parser = trace_subparsers.add_parser("list", help="List traces via TraceQL filters./TraceQL フィルタでトレースを一覧")
    list_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    list_parser.add_argument("--traceql", help="TraceQL-like query string./TraceQL 風クエリ")
    list_parser.add_argument(
        "--format",
        choices=("table", "json", "markdown"),
        default="table",
        help="Output format (table/json/markdown)./出力形式 (table/json/markdown)",
    )
    list_parser.set_defaults(func=handle_trace_list)

    show_parser = trace_subparsers.add_parser("show", help="Show spans for a trace./トレースの span を表示")
    show_parser.add_argument("trace_id", nargs="?", help="Trace identifier./トレース ID")
    show_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    show_parser.add_argument("--traceql", help="TraceQL filter (supports trace_id)./trace_id 指定に対応する TraceQL フィルタ")
    show_parser.add_argument(
        "--format",
        choices=("table", "json", "tree"),
        default="table",
        help="Output format (table/json/tree)./出力形式 (table/json/tree)",
    )
    show_parser.add_argument(
        "--include-events",
        dest="include_events",
        action="store_true",
        default=True,
        help="Include span events./イベントを含める",
    )
    show_parser.add_argument(
        "--no-events",
        dest="include_events",
        action="store_false",
        help="Skip events./イベントを省略",
    )
    show_parser.set_defaults(func=handle_trace_show)

    search_parser = trace_subparsers.add_parser("search", help="Search spans via TraceQL filters./TraceQL フィルタで span を検索")
    search_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    search_parser.add_argument("--traceql", help="TraceQL filter supporting attributes./属性条件に対応する TraceQL フィルタ")
    search_parser.add_argument("--limit", type=int, help="Maximum spans to return./返却する span の最大数")
    search_parser.add_argument(
        "--format",
        choices=("table", "json", "markdown"),
        default="table",
        help="Output format (table/json/markdown)./出力形式 (table/json/markdown)",
    )
    search_parser.add_argument(
        "--status",
        choices=("OK", "ERROR"),
        help="Filter spans by status./status 別にフィルタ",
    )
    search_parser.add_argument(
        "--timeout-only",
        action="store_true",
        help="Return only spans with timeout flag./timeout 属性を持つ span のみ",
    )
    search_parser.set_defaults(func=handle_trace_search)

    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """CLI main entry./CLI メインエントリ"""

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(file=stdout)
        return 1
    return args.func(args, stdout=stdout, stderr=stderr)


def app() -> None:
    """Console script entrypoint./コンソールスクリプトのエントリポイント"""

    sys.exit(main())


__all__ = ["app", "main"]
