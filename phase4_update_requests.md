# Phase 4 Update Requests – Runtime Reliability & Tracing Expansion

## 0. 背景と目的
- フェーズ3で CLI と TraceQL 風クエリを整備した結果、実運用に近い形で利用するユーザーが増える見込み。
- 次のフェーズではフローランタイムの堅牢化とトレーシング機能の拡充を並行して進め、実行失敗や調査コストを最小化する。
- 既存ガイドライン（Fail-Fast / Log & Recover の明示、テストチェックリストの活用）と整合しつつ、設計レビューなしに新しい設定項目を増やさない。

## 1. 必須対応 (Must)
- [ ] `Policy`（Fail-Fast / Retry / Timeout / OnError）に対する構文・値検証を実装し、CLI と Python API の両方でバリデーションエラーを早期に返却する。
- [ ] フローノード実行での例外情報（失敗ノード名、入力 payload サマリ、ポリシー設定）を集約し、トレーサーへ Span 属性として送出・ログへ出力する。
- [ ] トレース永続化（SQLiteTracer）で `span.status`・`error`・`policy_snapshot` を保存し、既存の TraceQL クエリから参照できるようにする。
- [ ] CLI `illumo trace list/show/search` に `--format json|table|markdown` を追加し、失敗トレースの抽出を簡易化する。
- [ ] `illumo run` の exit code と標準出力で、失敗時に Trace ID・失敗ノード・要因概要を必ず表示する（CI で即座に原因を特定できる状態にする）。

## 2. 優先対応 (Should)
- [ ] 再実行ダイアリー（`runtime_execution.log` のようなファイル）を追加し、再実行時に直前の失敗ノードと入力値を参照できるようにする。
- [ ] Timeout ポリシー適用時に Span へ `timeout=true` を付与し、TraceQL 検索で即抽出できるようにする。
- [ ] テストチェックリスト（`docs/test_checklist*.md`）へフェーズ4向けの項目を追記し、単発テスト（`pytest tests/test_flow_examples.py::TestCase` など）とトレース確認を紐づける。
- [ ] README / README_ja / トレーサー関連ドキュメントへ、失敗トレースの確認手順と CLI フォーマット例を追加する。

## 3. 検討事項 (Could)
- [ ] トレーシングのサマリーレポート（最新 N 件の失敗トレースを Markdown で出力）の自動化。
- [ ] トレーサーに書き込むイベントのストリーミング（`ConsoleTracer` をサンプルとして SSE/TUI で可視化）を評価する。
- [ ] `illumo run --resume TRACE_ID` のような簡易再実行フラグを検討し、設計コストとメリットを比較する。

## 4. 実装ガイドライン
- ランタイムのバリデーションは `src/illumo_flow/runtime/` 配下の既存ロジックへ追記し、例外メッセージは英語/日本語の併記コメントスタイルを踏襲する。
- トレーサー拡張は `SQLiteTraceReader` / `SQLiteTracer` を中心に行い、既存スキーマの互換性を維持したままカラム追加を検討する（マイグレーションが必要な場合は設計レビューを明記）。
- CLI の出力フォーマット変更は `illumo_flow/cli` の共通ユーティリティでまとめ、既存サブコマンドの挙動を壊さないようにテストを追加する。
- 追加されるログファイルやトレースエクスポート機能は `.venv` 外のワークスペース内に限定し、ユーザーが `--output-dir` 等で制御できるよう配慮する。

## 5. インターフェース / コマンド設計
### 5.1 Python API
- `illumo_flow.runtime.PolicyValidator`（新規クラス）
  - `validate(policy: Policy) -> None`：不正値がある場合 `PolicyValidationError` を送出。
  - `from_dict(config: Mapping[str, Any]) -> Policy`：CLI などからの辞書入力を正規化。
- `PolicyValidationError(Exception)`：`errors: list[str]` プロパティと `__str__` を実装。
- `RuntimeExecutionReport`（新規データ構造）
  - `trace_id: str`
  - `failed_node_id: Optional[str]`
  - `summary: str`
  - `policy_snapshot: Mapping[str, Any]`
  - `context_digest: Mapping[str, Any]`
- `FlowRuntime.run(..., report: Optional[RuntimeExecutionReport] = None) -> Context`
  - 実行結果と併せて `report` を更新し、CLI / ユーザーコードが失敗サマリを参照できるようにする。
  - 既存シグネチャへの後方互換性を保つため、キーワード専用パラメータとして追加。

### 5.2 CLI コマンド
- `illumo run`
  - 新フラグ `--report-path PATH`：失敗時に `RuntimeExecutionReport` を JSON または Markdown で書き出す。
  - 新フラグ `--report-format {json,markdown}`：書き出し形式を選択（既定は `json`）。
  - 標準出力（失敗時）例
    ```
    Flow failed.
      trace_id: 6d7b...
      failed_node: transform
      reason: Retry max attempts exceeded
      policy: fail_fast=True, retry=exponential(max_attempts=2, delay=500ms)
    ```
  - Exit code: 成功は 0、失敗は 1 を明示。
- `illumo trace list`
  - 既存オプションに `--format {table,json,markdown}` を追加（既定は `table`）。
  - `--status {OK,ERROR}` フィルタで失敗トレースを素早く抽出。
- `illumo trace show`
  - `--format {tree,json}` を追加。`tree` は親子関係を ASCII でレンダリング。
  - `--include-events` フラグで span events を併記（既定は off）。
- `illumo trace search`
  - `--format` を追加し、他コマンドと統一。
  - `--timeout-only` フラグで `span.attributes["timeout"] == true` をショートカット検索。
- 共通オプション
  - `--limit` は既定 50。過剰データ取得を避けるため上限 500 を設定。
  - `--no-color` で彩色出力を抑制（CI ログ向け）。

### 5.3 トレーススキーマ / ファイルレイアウト
- SQLite `spans` テーブルに以下のカラムを追加想定
  - `status TEXT`（既存値を移行）
  - `error TEXT`（失敗理由サマリ）
  - `policy_snapshot TEXT`（JSON 文字列）
  - `timeout INTEGER DEFAULT 0`
- 追加カラムは `ALTER TABLE` で後方互換を維持し、マイグレーション手順をドキュメントに記載。
- `runtime_execution.log`（Should対応）が生成されるディレクトリ構造
  - 既定: `./logs/runtime_execution.log`
  - `--output-dir` 指定時: `${output_dir}/runtime_execution.log`

## 6. ユーザー提供方法
- `pip install illumo-flow` 更新で CLI / ランタイム機能が利用可能になるよう、リリースノートにフェーズ4の変更点を明記する。
- README / README_ja、`docs/tutorials/07_tracer_playground*.md` に新機能の手順を追加し、CLI 例と TraceQL クエリの実行結果を手順形式で提示する。
- 失敗事例の CLI 出力とトレース検索パターンを `examples/` 内のフローと紐付け、ユーザーがダウンロード直後に再現できるようにする。
- 必須対応が完了した段階で `phase4_update_plan.md` を用意し、残タスクとテスト状況を記録する（チェックリストへの記入も平行して実施）。
