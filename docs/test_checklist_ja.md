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
- [x] tests/test_flow_examples.py::test_router_agent_selects_route_with_reason — RouterAgentが選択結果と理由を記録することを確認
- [x] tests/test_flow_examples.py::test_evaluation_agent_records_score_and_metadata — EvaluationAgentがスコア・理由・構造化データを保存することを確認
- [x] tests/test_flow_examples.py::test_console_tracer_emits_flow_and_node_spans — ConsoleTracerがフロー・ノードの開始/終了メッセージを出力することを確認
- [x] tests/test_flow_examples.py::test_sqlite_tracer_persists_spans — SQLiteTracerがspan情報を永続化することを確認
- [x] tests/test_flow_examples.py::test_otel_tracer_exports_spans — OtelTracerがエクスポーターへspanを送信することを確認
- [ ] CLI手動確認 — `illumo run` による `--tracer`／Policy 上書きの動作確認を実施
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_collects_selected_files — WorkspaceInspectorNode が選択ファイルのプレビューを取得することを確認
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_filters_by_extension — 許可外拡張子が除外され理由が記録されることを確認
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_respects_max_bytes — ファイルサイズ上限超過でプレビューを空にし除外理由を残すことを確認
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_rejects_missing_root — ルート不在時に FlowError が送出されることを確認
- [x] tests/test_workspace_nodes.py::test_patch_node_applies_diff_without_writing — 統一diffを適用してもディスクを変更しないことを確認
- [x] tests/test_workspace_nodes.py::test_patch_node_respects_allowed_paths — 許可されないパスへのパッチを拒否することを確認
- [x] tests/test_workspace_nodes.py::test_patch_node_write_option — `write` 指定時のみディスクへ適用されることを確認
- [x] tests/test_workspace_nodes.py::test_test_executor_runs_pytest — 対象ワークスペースで pytest を実行し結果を取得できることを確認
- [x] tests/test_workspace_nodes.py::test_test_executor_records_failures — 非ゼロ終了コードでも例外なく結果を記録することを確認
- [x] tests/test_workspace_nodes.py::test_summary_agent_compiles_report — 作業内容・テスト結果・レビュー要約を取りまとめることを確認
