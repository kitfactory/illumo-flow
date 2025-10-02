# Phase 2 Update Plan Checklist

## ガバナンス
- [ ] `phase2_update_requests.md` の更新を常に参照し、対応完了後に該当チェックボックスを更新する。
- [ ] 実装ごとに小さなコミットを作成し、テスト通過後に push する。
- [ ] テストは 1 ファイルずつ実行し、結果を `docs/test_checklist.md` / `docs/test_checklist_ja.md` に記録してから次へ進む。

## フロー
- [ ] 対象タスクの設計付録（A/B/C/D）を確認し、不明点があれば追記してレビューする。
- [ ] 影響範囲とコンテキスト設計を把握してから実装を開始する。

## ターゲット別実装サイクル（各タスクごとに繰り返す）
1. スケルトン作成
   - [x] 必要なモジュール／クラスを追加・修正（責務ごとに分割）。
   - [x] dataclass / Protocol / NodeConfig を定義する。
2. ユニットテスト追加
   - [x] 既存テストファイルにケースを追記（新規ファイルは最小限）。
   - [x] 対象テストファイルのみ実行（例: `pytest tests/test_workspace_inspector.py -q`）。
   - [x] テスト結果をテストチェックリストに記録する。
3. CLI 動作確認
   - [x] `illumo run ...` で該当 YAML を実行。
   - [x] ConsoleTracer / SQLiteTracer のログを確認し、問題があれば修正。
4. ドキュメント更新
   - [x] `docs/tutorials/` や README に手順・注意点を追記する。
   - [x] `phase2_update_requests.md` の該当項目にチェックを入れる。

## テスト運用ルール
- [ ] 各テスト実行後に `docs/test_checklist*.md` へ結果を記録する。
- [ ] テストが失敗した場合は修正後に再実行し、成功するまで次へ進まない。

## タスク別チェックリスト

### 1.1 コーディング補助エージェント
- [x] WorkspaceInspectorNode 実装 + テスト + CLI 検証。
- [x] PatchNode 改修 + テスト + CLI 検証。
- [x] TestExecutorNode 実装 + テスト + CLI 検証。
- [x] SummaryAgent 実装 + レポート出力確認。
- [x] サンプルプロジェクト（`sample_app/`）と YAML を整備。
- [x] ドキュメント更新（README / tutorials / examples README）。

### 1.1 TracerDB インターフェース（SQLite / Tempo）
- [x] TracerDB Protocol 定義。
- [x] SQLiteTracerDB 実装 + テスト + CLI 検証。
- [x] TempoTracerDB 実装 + テスト + CLI 検証。
- [x] 既存トレーサーを TracerDB 化し、後方互換性を確認。
- [ ] ドキュメント更新（設定例・ベストプラクティス）。

### 2. チャットボット事例
- [ ] HandoffNode / AuditNode 実装 + テスト。
- [ ] FAQ データと YAML を `examples/multi_agent/chat_bot/` に配置。
- [ ] CLI シナリオ（FAQ 応答 / エスカレーション）を実行。
- [ ] ドキュメント更新（チュートリアル・README）。

### 2. SummaryAgent
- [x] SummaryAgent 単体テスト。
- [x] マルチエージェントフローへの統合テスト。
- [x] CLI 出力／保存ファイルの確認。
- [x] ドキュメント更新（利用手順と出力例）。

## 完了条件
- [ ] `phase2_update_requests.md` の必須・優先タスクがすべてチェック済み。
- [ ] `docs/test_checklist*.md` に対象テストがすべて記録済み。
- [ ] README / チュートリアル / examples README が最新内容と一致。
