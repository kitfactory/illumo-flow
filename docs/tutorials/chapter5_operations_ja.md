# 第5章 · 設定・テスト・運用

保守観点として設定管理・テスト戦略・運用ガードを整理します。

## 5.1 設定管理
- フロー定義は YAML / JSON などで管理しレビュー可能にする。
- Python DSL と設定ファイルの内容を同期させ、環境差異を抑える。
- 呼び出し関数はインポート文字列（`examples.ops.extract` 等）で指定し、宣言的に保つ。

```yaml
flow:
  entry: ingest
  nodes:
    ingest:
      type: illumo_flow.core.FunctionNode
      name: ingest
      context:
        inputs:
          callable: my_project.nodes.ingest
        outputs: $ctx.data.ingested
    normalize:
      type: illumo_flow.core.FunctionNode
      name: normalize
      context:
        inputs:
          callable: my_project.nodes.normalize
          payload: $ctx.data.ingested
        outputs: $ctx.data.normalized
  edges:
    - ingest >> normalize
```

## 5.2 テスト戦略
- `docs/test_checklist_ja.md` のチェックリストを用い、pytest を 1 ケースずつ実行する。
- モックよりも実ペイロードを優先し、決定的なシナリオを作る。
- ルーティングやコンテキストへの書き込みも検証対象に含める。

## 5.3 運用時の注意
- デバッグ時は `FLOW_DEBUG_MAX_STEPS` でループ回数を制限する。
- ルーティングでは `confidence` / `reason` を記録し、意思決定の監査に備える。
- コンテキスト書き換えは最小に留め、可能ならペイロード変換で表現する。
- 外部サービス連携ではノード内でリトライなどを実装し、失敗は明確に外へ伝える。

## 5.4 次のステップ
- `docs/flow_ja.md` で API 詳細や高度なパターンを確認する。
- `examples/` ディレクトリの CLI/DSL サンプルを実際に動かして理解を深める。
- 新しいテストを追加したらチェックリストも更新する。
