# テストチェックリスト

テストは常に 1 件ずつ実行し、ここで進捗を管理します。

## 運用ガイドライン
- シナリオの追加・修正は `tests/test_flow_examples.py` 内に限定します（本リポジトリは編集のみ許可）。
- 実行前に対象テストをすべて下記チェックリストへ列挙します。
- 各ケースは `pytest tests/test_flow_examples.py::TEST_NAME` で個別に実行し、ループ系を検証するときはハング防止で `FLOW_DEBUG_MAX_STEPS=200` を設定します。
- 成功したテストはチェックボックスへチェックを入れます。回帰テストを始める際は全項目を未チェックへ戻し、順番に実行します。
- テストを追加したら新しい項目を追加し、削除した場合はチェックリストからも除去します。

## チェックリスト（回帰前に未チェックへリセット）
- [x] tests/test_flow_examples.py::test_examples_run_without_error — 同梱 DSL シナリオのスモーク実行を確認
- [x] tests/test_flow_examples.py::test_join_node_receives_parent_dictionary — 複数親ノードからのペイロード集約を検証
- [x] tests/test_flow_examples.py::test_context_paths_are_honored — `inputs` と `outputs` が共有コンテキストへ正しくマッピングされることを確認
- [x] tests/test_flow_examples.py::test_multiple_outputs_configuration — 1 ノードで複数出力先へ書き込めることを検証
- [x] tests/test_flow_examples.py::test_flow_from_yaml_config — YAML と辞書設定からフローを構築・実行できることを確認
- [x] tests/test_flow_examples.py::test_expression_inputs_and_env — テンプレート式と環境変数解決の動作を検証
- [x] tests/test_flow_examples.py::test_callable_resolved_from_context_expression — コンテキストから動的にコール可能を取得する処理を確認
- [x] tests/test_flow_examples.py::test_function_node_returning_routing_is_rejected — FunctionNode が Routing 返却を拒否することを検証
- [x] tests/test_flow_examples.py::test_loop_node_iterates_over_sequence — ループノードがイテラブルを順に処理することを確認
- [x] tests/test_flow_examples.py::test_get_llm_appends_v1_suffix_when_missing — OpenAI互換ホストに自動で`/v1`サフィックスを付与することを確認
- [x] tests/test_flow_examples.py::test_get_llm_keeps_existing_v1_suffix — 既に`/v1`が付与されたbase URLが変更されないことを確認
- [x] tests/test_flow_examples.py::test_get_llm_defaults_to_openai_when_unspecified — ヒントがない場合にOpenAIプロバイダへフォールバックすることを確認
- [x] tests/test_flow_examples.py::test_get_llm_respects_explicit_provider_priority — 明示指定したプロバイダがヒューリスティックより優先されることを確認
- [x] tests/test_flow_examples.py::test_agent_openai_writes_to_configured_paths — OpenAIベースのAgentが指定パスへ応答を保存することを確認
- [x] tests/test_flow_examples.py::test_agent_lmstudio_writes_to_agents_bucket — LMStudioベースのAgentがパス未指定時に`ctx.agents.<id>`へ保存することを確認
