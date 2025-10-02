# Phase 4 Update Plan – Runtime Reliability & Tracing Expansion

## 1. 概要
- **目的**: フェーズ4の Must/Should 要件を実装し、フローランタイムの堅牢化とトレーシング機能拡充を完了する。
- **参照**: `phase4_update_requests.md`
- **進行管理**: チェックリスト方式で Must → Should の順に進め、各ステップでテストとドキュメント更新を必ず行う。

## 2. タスク分解

### 2.1 Policy バリデーション
- [ ] `PolicyValidator` と `PolicyValidationError` の実装。
- [ ] `FlowRuntime.configure` / `FlowRuntime.run` からバリデーション呼び出しを追加。
- [ ] CLI からのポリシー読み込みでエラーを表示（`illumo run`）。
- [ ] 単体テスト追加（正常系・異常系）。

### 2.2 実行失敗サマリ & RuntimeExecutionReport
- [ ] `RuntimeExecutionReport` データ構造の追加。
- [ ] Flow 実行中に失敗情報を収集し、トレーサー/ログへ送出。
- [ ] `FlowRuntime.run(..., report=...)` パラメータを実装。
- [ ] CLI 出力と `--report-path` / `--report-format` を追加。
- [ ] テスト（CLI & Python API）で失敗サマリが出力されることを確認。

### 2.3 トレーシング永続化拡張
- [ ] `SQLiteTracer` へのカラム追加（`status`, `error`, `policy_snapshot`, `timeout`）。
- [ ] マイグレーション手順の策定とドキュメント追記。
- [ ] `SQLiteTraceReader` / TraceQL サーフェスの更新。
- [ ] テスト: 既存 DB との互換性、カラム追加後の読み書き。

### 2.4 CLI トレースコマンド強化
- [ ] `illumo trace list` へ `--format` / `--status` を追加。
- [ ] `illumo trace show` へ `--format` / `--include-events` を追加。
- [ ] `illumo trace search` へ `--format` / `--timeout-only`（TraceQL ショートカット）を追加。
- [ ] 共通出力フォーマッタの実装とテスト。

### 2.5 再実行ダイアリー & Timeout 属性（Should）
- [ ] `runtime_execution.log` の書き出し機構。
- [ ] Timeout 発生時の Span 属性 `timeout=true` を追加。
- [ ] CLI オプションでログディレクトリ変更をサポート。
- [ ] テスト: Timeout ケースと再実行ログの生成確認。

### 2.6 ドキュメント更新
- [ ] README / README_ja に失敗サマリ・トレース確認の手順を追記。
- [ ] `docs/tutorials/07_tracer_playground*.md` を CLI ベースに更新。
- [ ] `docs/test_checklist*.md` にフェーズ4項目を追加。

## 3. テスト計画
- `tests/test_flow_examples.py` にフェーズ4向けケースを追記（新規ファイルは作成しない）。
- `tests/test_tracing_db.py` にカラム追加に関するテストを追加。
- CLI テスト（Typer/pytest）で `illumo run` `illumo trace list/show/search` を検証。
- `docs/test_checklist.md` / `_ja.md` を使用し、1ケースずつ記録。

## 4. 完了条件
- Must タスクがすべて完了し、単体テストがグリーン。
- README / ドキュメントが更新され、フェーズ4機能の手順が記載されている。
- `illumo` CLI 新オプションとトレーサー拡張が `pip install` 直後に動作確認できる。
- `phase4_update_requests.md` の各項目が満たされていることをチームレビューで確認。
