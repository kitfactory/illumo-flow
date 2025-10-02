# Coding Assistant Demo

このサンプルはフェーズ2で追加したワークスペース関連ノードを組み合わせ、バグ修正フローを再現します。

## ディレクトリ構成

```
examples/multi_agent/coding_assistant/
├─ coding_assistant.yaml          # フロー定義
├─ example_diff.patch             # 修正案のサンプル diff
└─ sample_app/
   ├─ __init__.py                 # バグ混入コード（add が減算している）
   └─ tests/test_sample_app.py    # pytest テスト
```

## 実行手順

1. **差分の確認**: `example_diff.patch` が add 関数のバグを修正する差分です。任意の diff を用意する場合は `ctx.diff.proposed` に渡してください。
2. **フローの実行**:

   ```bash
   illumo run examples/multi_agent/coding_assistant/coding_assistant.yaml \
     --context '{
       "request": {
       "description": "Fix add() implementation",
        "target_root": "examples/multi_agent/coding_assistant",
        "tests": "pytest -q"
      },
       "diff": {
         "proposed": "'"$(cat examples/multi_agent/coding_assistant/example_diff.patch | python -c "import sys, json; print(json.dumps(sys.stdin.read()))")"'"
       }
     }'
   ```

   上記コマンドでは JSON の埋め込みを簡略化するために Python ワンライナーで diff をエスケープしています。環境に応じて diff の渡し方を調整してください。

3. **dry-run と書き込み**:
   - デフォルトでは PatchNode は diff を適用してもディスクを書き換えません。結果は `ctx.workspace.files` に格納されます。
   - テストを修正後のコードで実行したい場合は、コンテキストに `"write": true` を追加してから再度実行してください。書き込み後は手動でファイルを元に戻すことを推奨します。

4. **出力の確認**:
   - SummaryAgent が `ctx.summary.report` に人間向けレポートを、`ctx.summary.structured` に構造化データを生成します。
   - テスト結果は `ctx.tests.results` に格納され、`stdout` / `stderr` も参照できます。

## ノード構成

- `WorkspaceInspectorNode` : 対象ディレクトリ配下のファイル一覧とプレビューを収集します。
- `PatchNode` : 提供された統一 diff を適用し、`write` フラグが無い限りディスクを変更せず差分を確認できます。
- `TestExecutorNode` : pytest を実行し、結果・stdout/stderr・実行時間を記録します。
- `SummaryAgent` : 変更内容、テスト結果、レビュー情報をもとにサマリーレポートを作成します。

## 注意事項

- LLM を用いた差分生成やレビューは別途 Agent を組み合わせて実装してください。本サンプルでは diff を外部入力としています。
- `allowed_paths` に含まれないファイルへ差分を適用すると FlowError になります。
- `timeout` や `allowed_extensions` などの設定は YAML で調整可能です。
