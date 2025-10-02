# Phase 3 実装計画

## 前提と準備
- `uv venv --seed` で `.venv` を初期化し、`source .venv/bin/activate` を実行してから着手する。
- 依存追加は最小限に抑え、既存環境で不足する場合のみ `uv add <pkg>` を検討しつつ `uv pip install -e .` で編集モードを維持する。
- 着手前に `pytest tests/test_flow_examples.py::test_sqlite_tracer_persists_spans` を実行してトレーサ関連の既存挙動が正常であることを確認し、失敗した場合は先に解消する。
- テスト実行ごとに `docs/test_checklist.md` / `docs/test_checklist_ja.md` の対象項目を一件ずつ更新し、チェックが付くまでは次工程へ進まない。

## ステップ 1: CLI エントリーポイントの骨組み
- `illumo_flow/cli/__init__.py` に argparse ベースの CLI を定義し、`pyproject.toml` の `project.scripts` へ `illumo = "illumo_flow.cli:app"` を追加する。
- `illumo run`/`illumo trace` のサブコマンド定義だけを用意し、処理本体は未実装のまま `NotImplementedError` で一旦固定する。
- 変更後に `pytest tests/test_flow_examples.py::test_examples_run_without_error` を実行し、基礎フローの動作が壊れていないか確かめる。通過しない場合は修正完了まで次に進まない。

## ステップ 2: `illumo run` 実装
- CLI から Flow 設定を受け取り `Flow.from_config` で読み込み、コンテキスト JSON を文字列/`@path`/stdin で受け分ける処理を追加する。
- `--tracer` / `--policy` / `--set` オプションを `FlowRuntime.configure` に反映させ、終了コードと標準出力/標準エラーの整備を行う。
- `tests/test_flow_examples.py` に CLI 実行をサブプロセスで検証するテストケースを追記し、成功終了とエラー終了の双方を確認する。
- テストは個別に `pytest tests/test_flow_examples.py::test_cli_run_happy_path`（新規追加テスト名想定）→`pytest tests/test_flow_examples.py::test_cli_run_reports_failure` の順に実行し、両方が通るまで次工程へ進まない。
- `docs/test_checklist.md` / `_ja` に追加したテスト分のチェックボックスを増やし、実行後に完了状態へ更新する。

## ステップ 3: Trace ストレージ読み出しの共通化
- `SQLiteTraceReader` を CLI から再利用できるようにラッパー関数を `illumo_flow/tracing_db.py` 付近へ追加し、DB パス解決とリソースクローズを共通化する。
- CLI の `--db` オプションでデフォルト `illumo_trace.db` を上書きできるようにし、存在しない場合の Fail-Fast 例外を整備する。
- 既存の `tests/test_tracing_db.py::test_sqlite_trace_reader_lists_spans_and_events` を拡張して CLI ヘルパー経由でも同じ結果を返すことを確認する。
- 対象テストを `pytest tests/test_tracing_db.py::test_sqlite_trace_reader_lists_spans_and_events` と個別実行し、パスするまで次工程へ進まない。

## ステップ 4: TraceQL ベースの `trace list/show/search`
- `illumo trace list` に `--traceql` オプションを追加し、`traces{} | pick(...) | limit ...` のようなクエリを `SQLiteTraceReader` へ渡して TraceID とタイムスタンプを取得する。
- `illumo trace show` では `trace_id = "..."` 条件を強制し、単一トレースの Span/イベントを描画する。
- `illumo trace search` では `span.attributes["node_id"] == "inspect"` 等の属性条件をサポートし、ヒット結果を `--limit` で制御する。
- `tests/test_tracing_db.py` に TraceQL 指向の CLI テスト（例えば `test_cli_trace_list_with_traceql` / `test_cli_trace_search_by_attribute`）を追加し、クエリ文字列が適切に変換されるか確認する。
- 新規テストを一つずつ `pytest tests/test_tracing_db.py::test_cli_trace_list_with_traceql` → `pytest tests/test_tracing_db.py::test_cli_trace_search_by_attribute` の順で実行し、成功するまでは次へ進まない。

## ステップ 5: ドキュメントとチェックリスト整備
- `README.md` / `README_ja.md` の Quickstart を CLI ベースの手順に置き換え、旧ワンライナーの記載を削除する。
- `docs/tutorials/07_tracer_playground.md` 等のトレーサ関連ドキュメントを更新し、TraceQL ベースの CLI 手順へ差し替える。
- `phase2_update_plan.md` / `phase2_update_requests.md` の CLI メモを Phase3 前提に統合し、重複や旧情報を整理する。
- ドキュメント更新後は `pytest tests/test_flow_examples.py::test_console_tracer_emits_flow_and_node_spans` と `pytest tests/test_tracing_db.py::test_sqlite_trace_reader_filters_by_trace_id` を順に実行し、実装影響による退行が無いことを確認する。通過しない場合は戻って原因を解消する。

## ステップ 6: 仕上げとパッケージ検証
- CLI 一式を `illumo run` で実際の例 (`examples/sample_flows.py`) に対して動作確認し、TraceDB を生成して TraceQL コマンドが期待通り出力することを確認する。
- `pytest` で追加・既存の全対象テストをチェックリスト順に再走し、全テストがグリーンであることを記録する。`pytest tests/test_flow_examples.py::test_cli_run_happy_path` など CLI 関連テストは重ねて確認する。
- `pip install .` をローカル仮想環境内で試し、インストール後に `illumo --help` / `illumo trace list --traceql 'limit 1'` を実機確認する。必要であれば `illumo run` コマンドで JSON 出力が得られることを確かめる。
- すべて完了したら `docs/test_checklist.md` / `_ja` の CLI 手動チェック項目を `illumo` ベースの手順へ更新し、実施済みであることを明記する。
