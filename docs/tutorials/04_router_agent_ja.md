# 4. RouterAgent – 分岐の決め手

## 目標
`RouterAgent` で “Ship” か “Refine” などの選択を LLM に任せ、理由とともに記録します。

## ワクワクする理由
- 条件分岐が会話ベースになり、ロジックが自然言語で定義できます。
- `ctx.route.reason` に理由が残るので、意思決定のトレースも容易。

## キー概念
- `choices` で候補を列挙、応答から自動マッチング。
- `output_path` / `metadata_path` への保存。
- `ctx.routing.<id>` に時系列ログが残る。

## ハンズオン
```python
from illumo_flow import RouterAgent, NodeConfig

router = RouterAgent(
    config=NodeConfig(
        name="Decision",
        setting={
            "prompt": {"type": "string", "value": "Context: {{ $ctx.review }}\nChoose Ship or Refine."},
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

router.bind("decision")
ctx = {"review": "Tests are green and stakeholders approved."}
routing = router._execute({}, ctx)

print(routing.target, routing.reason)
print(ctx["route"]["decision"], ctx["route"]["reason"])
print(ctx["routing"]["decision"])
```

## チェックリスト
- [ ] 選択結果が `choices` のどれかである。
- [ ] `ctx.route` に結果と理由が保存される。
- [ ] `ctx.routing.decision` に履歴が蓄積される。

次章では EvaluationAgent でスコア付けを行い、さらにリッチなフローに発展させます。
