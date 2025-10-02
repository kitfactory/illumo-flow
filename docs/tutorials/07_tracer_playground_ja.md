# 7. トレーサー道場 – フローの裏側を見る

## やりたいこと
Flow と Node の span を観察し、`instruction` / `input` / `response` の色分けログや履歴を残したい。

### トレーサーを使う理由
- `ConsoleTracer` / `SQLiteTracer` / `OtelTracer` は同じ `TracerProtocol` 実装なので差し替えが瞬時にできます。
- ConsoleTracer はエージェントの `instruction` / `input` / `response` を色付きで表示し、進行状況を即座に把握できます。
- SQLite / OTEL へ送ることで、後から分析・監視基盤と連携できます。

## 手順
1. `FlowRuntime.configure(tracer=...)` で使いたいトレーサーを選択。
2. 第6章のミニアプリなど任意のフローを実行。
3. コンソールログ・SQLite DB・OTEL 転送結果を確認。

```python
from illumo_flow import FlowRuntime, ConsoleTracer, SQLiteTracer, OtelTracer
from illumo_flow.tracing_db import TempoTracerDB

# ConsoleTracer: 色付きで instruction/input/response を表示
FlowRuntime.configure(tracer=ConsoleTracer())

# SQLiteTracer: span をファイルに保存
FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))

# OtelTracer: 監視基盤へエクスポート
FlowRuntime.configure(
    tracer=OtelTracer(
        service_name="illumo-flow",
        db=TempoTracerDB(exporter=my_exporter),
    )
)
```

CLI から切り替える場合:

```bash
illumo run flow_launch.yaml --context '{"payload": {}}' --tracer sqlite --trace-db ./trace.db
illumo run flow_launch.yaml --context '{"payload": {}}' --tracer otel --service-name tracer-demo

# TraceQL 風クエリでトレースを検索
illumo trace list --traceql 'traces{} | pick(trace_id, root_service, start_time) | limit 5'
illumo trace search --traceql 'span.attributes["node_id"] == "inspect"'
illumo trace show --traceql 'trace_id == "TRACE"' --format tree

# 失敗サマリとタイムアウト span を抽出
illumo run flow_launch.yaml --context @ctx.json --report-path logs/failure.json --log-dir ./logs
illumo trace search --timeout-only --format json
```

`illumo run` は失敗時にトレース ID / 失敗ノード / ポリシー情報を含むサマリを表示します。`--report-path` / `--report-format` で JSON / Markdown のレポートを出力し、`--log-dir` で `runtime_execution.log` の保存先を切り替えられます。`trace list` / `trace show` / `trace search` は `--format table|json|markdown` を受け付け、`trace show --format tree` で DAG 表示、`trace search --timeout-only` でタイムアウト済み span を抽出できます。

## トレーサーの見どころ
- ConsoleTracer は `[FLOW]` span を白、`[NODE]` span をシアンで表示し、Agent の instruction/input/response は黄・青・緑で色分けします。
- SQLiteTracer は `spans` / `events` テーブルへ永続化するため、SQL を使ってリトライやルーティングの履歴を分析できます。
- OtelTracer は `exporter=my_exporter` で渡したエクスポーターにバッチ送信します（OTLP クライアントなど）。
- どのトレーサーも同じペイロードを受け取るため、切り替えてもビジネスロジックには影響しません。観測先だけが変わります。

### 出力例
ConsoleTracer で coding assistant フローを実行した場合:

```
[FLOW] start name=inspect
  [NODE] start name=inspect
  [NODE] end status=OK
  [NODE] start name=apply_patch
  [NODE] end status=OK
  [NODE] start name=run_tests
  [NODE] end status=OK
  [NODE] start name=summarize
  [NODE] end status=OK
[FLOW] end status=OK
```

SQLiteTracer (trace.db) では以下のようなテーブル行を確認できます。

```sql
sqlite> SELECT kind, name, status FROM spans ORDER BY start_time LIMIT 3;
flow|inspect|OK
node|inspect|OK
node|apply_patch|OK
```

## 実験アイデア
- まず ConsoleTracer で第6章のフローを動かし、次に SQLiteTracer に切り替えてリトライや分岐が DB 上でどう記録されるか比較しましょう。
- ConsoleTracer をラップして `kind="node"` の span のみを表示するカスタムトレーサーを作り、Agent 関連の動きに集中してみてください。
- OTEL 経由でダッシュボードに送り、EvaluationAgent の遅延が閾値を超えたらアラートを鳴らす設定を試すと本番運用のイメージを掴めます。

## この章で学んだこと
- トレーサーは `FlowRuntime.configure` の引数を変えるだけで差し替えられる。
- ConsoleTracer で `instruction` / `input` / `response` が色付き表示され、状況把握が容易になる。
- SQLiteTracer や OtelTracer を使うと履歴を保存したり監視システムへ送信できる。

第8章では Policy を使って失敗時の挙動をコントロールします。
