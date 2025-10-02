# 3. Flow 基礎 – ノードをつなげて処理を流す

## やりたいこと
Agent の出力を Python 関数へ渡し、CLI と Python の両方で実行できるフローを構築したい。

### `Flow` を使う理由
- `illumo_flow.core.Flow` は DSL のエッジを実行順序と入力評価にマッピングします。
- `inputs` / `outputs` の式でデータの流れを明示的に制御できます。

## 手順
1. Agent と FunctionNode を定義。
2. `Flow.from_dsl` または YAML でフローを作成。
3. 実行して `ctx` に結果が格納される様子を確認。

```python
from illumo_flow import Flow, FunctionNode, Agent, NodeConfig

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "prompt": {"type": "string", "value": "{{ $ctx.user.name }} さんへの挨拶文を作成"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
        },
    )
)

def post_process(payload):
    return payload.upper()

uppercase = FunctionNode(
    config=NodeConfig(
        name="ToUpper",
        setting={"callable": {"type": "string", "value": "path.to.module.post_process"}},
        inputs={"payload": {"type": "expression", "value": "$ctx.messages.greeting"}},
        outputs="$ctx.messages.shout",
    )
)

flow = Flow.from_dsl(
    nodes={"greet": greeter, "upper": uppercase},
    entry="greet",
    edges=["greet >> upper"],
)

ctx = {"user": {"name": "紗希"}}
flow.run(ctx)
print(ctx["messages"]["shout"])
```

## CLI / YAML 版
```yaml
flow:
  entry: greet
  nodes:
    greet:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "{{ $ctx.user.name }} さんへの挨拶文を作成"
        outputs: $ctx.messages.greeting
    upper:
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: path.to.module.post_process
          payload: $ctx.messages.greeting
        outputs: $ctx.messages.shout
  edges:
    - greet >> upper
```
```bash
illumo run flow.yaml --context '{"user": {"name": "紗希"}}'
```

## Flow の仕組み
- DSL パーサは `greet >> upper` をグラフ構造に変換し、`flow.run` を繰り返すときにはキャッシュを再利用します。
- 入力式は JSONPath 風に評価され、`$ctx.messages.greeting` のような入れ子キーでも安全に参照できます。
- 実行完了時に Tracer がルート span を閉じ、対応するトレーサー（SQLite / OTEL など）が `ctx` のスナップショットをメタデータとして記録します。
- YAML で定義したフローも CLI 経由で同じローダーが処理するため、Python で試したあとに YAML 化しても振る舞いは変わりません。

## 応用ヒント
- もう一つ FunctionNode を追加して、大文字変換後のメッセージを外部 API に送信し、そのレスポンスを `outputs` で記録してみましょう。第7章のトレーサーで可視化できます。
- `ToUpper` の後ろに Chapter 4 の `RouterAgent` をつなぎ（`upper >> route`）、条件に応じて別ノードへ分岐する構成を試してみてください。
- 大規模フローは `examples/flows/*.yaml` に保存して `illumo run` で読み込むと、チームメンバーと同じシナリオを簡単に共有できます。

## この章で学んだこと
- `Flow` はノード間のデータフローを明示的に制御する土台です。
- `inputs` / `outputs` を通じて、どの値がどのノードへ渡るかを管理できます。
- CLI と Python の両方から同じフローを実行・デバッグできる柔軟性があります。
