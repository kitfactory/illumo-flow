# Update Plan Checklist

> **方針メモ**: 各項目は「実装を反映し、関連テストが成功した時点」でのみチェックを入れる。未テスト・部分実装の段階では未完了のまま進める。

## 調査フェーズ
- [x] Flow/Node 実行境界と CLI・YAML ローダーの実装を調査し、Agent/Tracer/Policy を差し込める拡張ポイントを洗い出す
- [x] `get_llm()` など既存の LLM 取得経路と OpenAI Agents SDK の接続方式を比較し、モデル解決順序（OpenAI→Anthropic→Google→LMStudio→Ollama→OpenRouter）を再確認する
- [x] LLM テスト方針として OpenAI `gpt-4.1-nano` を標準、LMStudio `openai/gpt-oss-20b`（`http://192.168.11.16:1234`）を別プロバイダ検証に用い、Google/Anthropic/Ollama/OpenRouter は実装のみとする

- [x] `Agent` クラスの API/責務を確定し、既存 Node ライフサイクルへ統合する
- [x] `Agent` 用の pytest ケースを追記し（多重出力や `history_path` の検証を含む）、docs/test_checklist.md に該当項目を追加する
- [x] Agent 系テストは OpenAI `gpt-4.1-nano` を既定モデルとして実行し、別プロバイダ確認は LMStudio (`http://192.168.11.16:1234`, モデル `openai/gpt-oss-20b`) で行う
- [x] `Agent` テストを個別に実行してパスさせ、docs/test_checklist.md / docs/test_checklist_ja.md の該当行をチェックする
- [x] `RouterAgent` クラスの分岐ロジックと会話履歴参照を実装する
- [x] `RouterAgent` 専用テスト（選択結果と `metadata_path` の保存確認）を追加し、docs/test_checklist.md へ管理項目を追記する
- [x] `RouterAgent` テストをケース単位で実行し、チェックリストにパス結果を反映する
- [x] `EvaluationAgent` クラスで JSON 評価出力とスコア保存を実装する
- [x] `EvaluationAgent` テスト（`structured_path`、合否判定など）を追加し、docs/test_checklist.md に登録する
- [x] `EvaluationAgent` テストを実行してパスさせ、チェックリストを更新する

## Tracer クラス実装とテスト
- [x] OpenAI Agents SDK Tracer インターフェース準拠の抽象を整備し、FlowRuntime から注入する経路を設計する
- [x] `ConsoleTracer` アダプタを作成し、Flow/Node span が色分けで出力されることを保証する
- [x] `ConsoleTracer` のテスト（span start/end・イベント発火）を追加し、docs/test_checklist.md に項目を記載する
- [x] `ConsoleTracer` テストを実行してパスさせ、チェックリストを更新する
- [x] `SQLiteTracer` アダプタで span 永続化を実装する
- [x] `SQLiteTracer` のテスト（SQLite に記録されるか、既定パスの扱い）を追記し、docs/test_checklist.md を更新する
- [x] `SQLiteTracer` テストを実行してパスさせ、チェックリストに反映する
- [x] `OtelTracer` アダプタのエクスポート処理を実装する
- [x] `OtelTracer` テスト（モックエクスポーターでの span 送信確認）を追加し、docs/test_checklist.md へ登録する
- [x] `OtelTracer` テストを実行してパスさせ、チェックリストを更新する

## Policy 機能実装とテスト
- [x] グローバル `Policy` モデルと FlowRuntime 連携を実装し、fail_fast/timeout/retry/on_error の合成順序を確立する
- [x] Policy の基礎テスト（デフォルト fail_fast、および FlowRuntime.configure による上書き）を追加し、docs/test_checklist.md に追記する
- [x] Policy テストを実行してパスさせ、チェックリストを更新する
- [x] ノード個別ポリシーの上書きロジックを実装し、Flow 全体より優先されることを確認する
- [x] ノード個別ポリシーを検証するテストを追加し、docs/test_checklist.md に登録する
- [x] ノード個別ポリシーのテストを実行してパスさせ、チェックリストを更新する

## ドキュメント・運用整備
- [x] README.md / README_ja.md に新版の Agent/Tracer/Policy 使い方を反映する
- [x] docs/update_requirement.md・tutorial 系ドキュメントを実装内容に合わせて更新し、`>>` DSL や FlowRuntime の既定挙動を明文化する
- [ ] 変更後の CLI フロー（Tracer 切替や Policy 指定）を手動確認し、docs/test_checklist.md に手動確認用のチェック項目を追加する
