# 7. トレーサーでフローを観察する

## 目標
Console / SQLite / OTEL の各トレーサーを切り替え、フローの内部動作を可視化します。

## 面白さ
- `[FLOW]` / `[NODE]` ログで進行状況が一目でわかります。
- SQLite に残した span を分析したり、OTEL で外部監視に接続できます。

## ステップ
1. **ConsoleTracer（デフォルト）**
   ```python
   from illumo_flow import FlowRuntime, ConsoleTracer
   FlowRuntime.configure(tracer=ConsoleTracer())
   ```
   フローを実行するとターミナルに色付きログが表示されます。

2. **SQLiteTracer**
   ```python
   from illumo_flow import SQLiteTracer
   FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))
   ```
   実行後、SQLite を確認:
   ```python
   import sqlite3
   with sqlite3.connect("trace.db") as conn:
       for row in conn.execute("SELECT span_id, kind, status FROM spans"):
           print(row)
   ```

3. **OtelTracer**
   ```python
   from illumo_flow import OtelTracer
   FlowRuntime.configure(tracer=OtelTracer(service_name="illumo-flow", exporter=my_exporter))
   ```
   `my_exporter.export(spans)` を実装して Jaeger/TEMPO に送信。

4. **CLI で切り替え**
   ```bash
   illumo run flow_launch.yaml --tracer sqlite --tracer-arg db_path=./trace.db
   illumo run flow_launch.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317
   ```

## チェックリスト
- [ ] ConsoleTracer で `[FLOW]` `[NODE]` ログが表示される。
- [ ] SQLiteTracer の DB に span 情報が保存される。
- [ ] OtelTracer がエクスポーターへ span を送信する（ダッシュボードで確認）。

観察スキルを磨いたら、第8章で Policy を使って失敗時の挙動を制御しましょう。
