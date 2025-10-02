"""illumo CLI entrypoint for flow execution and trace inspection./フロー実行とトレース調査のための illumo CLI エントリーポイント"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence, TextIO

from illumo_flow import ConsoleTracer, Flow, FlowError, FlowRuntime
from illumo_flow.policy import Policy, _clone_policy, _merge_policy
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


def _build_policy(override: Optional[str], base: Policy) -> Policy:
    """Merge JSON override into base policy./ベースポリシーへ JSON の上書きを適用"""

    if override is None:
        return _clone_policy(base)
    payload = _load_json_payload(override, default=None)
    if payload is None:
        return _clone_policy(base)
    if not isinstance(payload, dict):
        raise CLIError("Policy override must decode to a JSON object")
    return _merge_policy(_clone_policy(base), payload)


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
    previous_policy = _clone_policy(previous_runtime.policy)

    try:
        desired_tracer = _resolve_tracer(args.tracer, args.trace_db, args.service_name)
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    try:
        merged_policy = _build_policy(args.policy, previous_policy)
    except CLIError as exc:
        stderr.write(f"{exc}\n")
        return 1

    tracer_to_use = desired_tracer if desired_tracer is not None else previous_runtime.tracer
    FlowRuntime.configure(
        tracer=tracer_to_use,
        policy=merged_policy,
        llm_factory=previous_runtime.llm_factory,
    )

    try:
        result_context = flow.run(context=context_data)
    except (FlowError, Exception) as exc:
        stderr.write(f"Flow execution failed: {exc}\n")
        return 1
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=_clone_policy(previous_policy),
            llm_factory=previous_runtime.llm_factory,
        )
        if args.tracer is not None:
            _close_tracer(desired_tracer)

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
        stdout.write("No traces found/トレースは見つかりませんでした\n")
        return 0

    _render_table(picks, rows, out=stdout)
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

    rows = [
        [
            span.span_id,
            span.parent_span_id,
            span.name,
            span.kind,
            span.status,
            span.start_time,
            span.end_time,
        ]
        for span in spans
    ]
    _render_table(
        ["span_id", "parent", "name", "kind", "status", "start_time", "end_time"],
        rows,
        out=stdout,
    )

    if not args.events:
        return 0

    events = reader.events(trace_id=target_id)
    if not events:
        stdout.write("No events recorded/イベントは記録されていません\n")
        return 0

    span_events: Dict[str, List[EventRecord]] = {}
    for event in events:
        span_events.setdefault(event.span_id, []).append(event)

    for span in spans:
        scoped = span_events.get(span.span_id)
        if not scoped:
            continue
        stdout.write(f"Events for span {span.span_id} ({span.name}):\n")
        _render_table(
            ["event_type", "level", "message", "timestamp"],
            (
                [event.event_type, event.level, event.message, event.timestamp]
                for event in scoped
            ),
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

    if effective_limit is not None:
        filtered = filtered[: effective_limit]

    if not filtered:
        stdout.write("No spans matched/一致する span はありませんでした\n")
        return 0

    rows = [
        [span.trace_id, span.span_id, span.name, span.kind, span.status]
        for span in filtered
    ]
    _render_table(["trace_id", "span_id", "name", "kind", "status"], rows, out=stdout)
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
    run_parser.set_defaults(func=handle_run)

    trace_parser = subparsers.add_parser("trace", help="Trace inspection commands./トレース調査コマンド")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command")

    list_parser = trace_subparsers.add_parser("list", help="List traces via TraceQL filters./TraceQL フィルタでトレースを一覧")
    list_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    list_parser.add_argument("--traceql", help="TraceQL-like query string./TraceQL 風クエリ")
    list_parser.set_defaults(func=handle_trace_list)

    show_parser = trace_subparsers.add_parser("show", help="Show spans for a trace./トレースの span を表示")
    show_parser.add_argument("trace_id", nargs="?", help="Trace identifier./トレース ID")
    show_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    show_parser.add_argument("--traceql", help="TraceQL filter (supports trace_id)./trace_id 指定に対応する TraceQL フィルタ")
    show_parser.add_argument("--events", dest="events", action="store_true", default=True, help="Include events./イベントも表示")
    show_parser.add_argument("--no-events", dest="events", action="store_false", help="Skip events./イベントを省略")
    show_parser.set_defaults(func=handle_trace_show)

    search_parser = trace_subparsers.add_parser("search", help="Search spans via TraceQL filters./TraceQL フィルタで span を検索")
    search_parser.add_argument("--db", type=Path, default=Path("illumo_trace.db"), help="Trace database path./トレース DB のパス")
    search_parser.add_argument("--traceql", help="TraceQL filter supporting attributes./属性条件に対応する TraceQL フィルタ")
    search_parser.add_argument("--limit", type=int, help="Maximum spans to return./返却する span の最大数")
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
