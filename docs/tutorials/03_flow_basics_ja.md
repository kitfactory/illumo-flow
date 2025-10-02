# 3. Flow 基礎 – ノードをつなげて処理を流す

## 目標
Agent と FunctionNode を DSL で連結し、CLI でも Python でも実行できるフローを作ります。

## 面白いところ
- LLM と決定的処理を自由に組み合わせられます。
- `greet >> upper` のような記法で流れが視覚的に把握できます。

## キー概念
- `Flow.from_dsl` と `Flow.from_config`（YAML / Python dict）
- `inputs`・`outputs` における `$ctx.*`・`$payload`・`$joins` の使い方
- CLI (`illumo run flow.yaml`) と Python API の両立

## ハンズオン
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
      name: Greeter
      context:
        inputs:
          prompt: "{{ $ctx.user.name }} さんへの挨拶文を作成"
        outputs: $ctx.messages.greeting
    upper:
      type: illumo_flow.core.FunctionNode
      name: ToUpper
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

## チェックリスト
- [ ] `inputs` が適切に関数へ渡されることを理解した。
- [ ] Python / CLI 両方から同じフローを実行した。
- [ ] 結果が設定したコンテキストに保存される。

次は RouterAgent を使って会話の分岐を楽しみます。
