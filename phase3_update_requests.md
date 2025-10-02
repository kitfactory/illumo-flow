# Phase 3 Update Requests – CLI イニシアチブ

## 0. 背景と目的
- フェーズ2でノード・Tracer 周りの基盤整備が完了したため、フェーズ3では公式 CLI を整備し、`illumo run` をはじめとした操作体験を統一する。
- CLI の導入により、ドキュメントで案内している python ワンライナーを置き換え、チーム内・CI/CD での再利用性を高める。

## 1. 必須対応 (Must)
- [ ] CLI 本体（`illumo` エントリーポイント）を実装し、少なくとも以下のサブコマンドを提供する。
  - `illumo run FLOW_PATH --context CONTEXT_JSON [--tracer ... --policy ...]`
  - `illumo trace list [--db trace.db]`
  - `illumo trace show TRACE_ID [--db trace.db]`
- [ ] CLI 実行で使用する JSON コンテキストの読み込み（文字列／`@path`／標準入力）をサポートする。
- [ ] `FlowRuntime.configure` 経由の tracer / policy 指定を CLI フラグから切り替えられるようにする。
- [ ] `illumo run` 実行結果の exit code（success=0, failure>0）とログ出力を整理し、CI で利用できる状態にする。

## 2. 優先対応 (Should)
- [ ] `phase2_update_requests.md` で案内していたワンライナーを CLI に差し替え、README / チュートリアルの CLI 例も `illumo run` へ統一する。
- [ ] Trace 検索コマンドで `SQLiteTraceReader` を利用し、`--span-id`, `--name`, `--kind`, `--limit` などのフィルタ機能を実装する。
- [ ] CLI 実行ログを `docs/tutorials/07_tracer_playground.md` に反映し、Console / SQLite / OTEL の切り替え手順を CLI ベースに置き換える。
- [ ] `phase2_update_plan.md`/`phase2_update_requests.md` の CLI メモを Phase3 用に整理し、重複記載を避ける。

## 3. 検討事項 (Could)
- [ ] `illumo policy lint` のような設定検証コマンドを追加し、YAML 内の Policy 設定をチェックする仕組みを検討。
- [ ] `illumo diff apply`（PatchNode を CLI から試せるエイリアス）の可能性を評価。
- [ ] CLI で LLM プロバイダの API Key を扱う際の安全な設定方法（`--env-from .env` 等）を検討。

## 4. 実装ガイドライン
- CLI 実装には Typer もしくは argparse を使用し、`illumo_flow/cli/__init__.py` をエントリーポイントとする。
- `pyproject.toml` に `illumo = "illumo_flow.cli:app"`（Typerの場合）などを設定し、`pip install illumo-flow` 後に `illumo` コマンドが利用できるようにする。
- `illumo run` サブコマンドの処理流れ:
  1. YAML/JSON の読み込み (`Flow.from_config`)
  2. コンテキストのロード（JSON 文字列／`@path`／stdin）
  3. `--tracer` / `--policy` / `--set` オプションで `FlowRuntime.configure` を上書き
  4. 実行結果の `ctx` を JSON で `--output` ファイル or stdout に書き出す
  5. 失敗時は exit code ≠ 0 / `stderr` に要約を表示
- `illumo trace` サブコマンドは `SQLiteTraceReader` を利用し、デフォルトで `illumo_trace.db` を参照。`--db` で変更可能。
- 単体テストとして `tests/test_cli_run.py` などを追加し、`illumo run` の基本動作・エラーハンドリング・トレース表示を確認する。

## 5. 作業の進め方（推奨）
1. CLI 雛形作成 (`illumo_flow/cli/__init__.py`) とテスト環境のセットアップ。
2. `run` コマンドの実装 → 単体テスト → 実フローでの CLI 動作確認。
3. `trace list/show` 実装 → SQLiteTraceReader と連携 → テスト追加。
4. ドキュメント更新（README, チュートリアル, Phase2/Phase3 ドキュメント）。
5. CLI 付きパッケージで `illumo run` が利用できることをフェーズ3完了条件に含める。
