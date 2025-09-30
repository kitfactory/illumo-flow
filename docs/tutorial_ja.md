
# Flow チュートリアル（クイックリファレンス）

詳細な章立てチュートリアルは [`docs/tutorials`](tutorials/README_ja.md) に移動しました。このファイルでは最小例のみを掲載し、各章のリンクをまとめています。

## 最小直列フロー
```python
from illumo_flow import Flow, FunctionNode, NodeConfig

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload):
    return {**payload, "normalized": True}

def load(payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(
        config=NodeConfig(
            name="extract",
            setting={"callable": {"type": "string", "value": f"{__name__}.extract"}},
            outputs={"raw": {"type": "expression", "value": "$ctx.data.raw"}},
        )
    ),
    "transform": FunctionNode(
        config=NodeConfig(
            name="transform",
            setting={"callable": {"type": "string", "value": f"{__name__}.transform"}},
            inputs={"payload": {"type": "expression", "value": "$ctx.data.raw"}},
            outputs={
                "normalized": {"type": "expression", "value": "$ctx.data.normalized"}
            },
        )
    ),
    "load": FunctionNode(
        config=NodeConfig(
            name="load",
            setting={"callable": {"type": "string", "value": f"{__name__}.load"}},
            inputs={
                "payload": {"type": "expression", "value": "$ctx.data.normalized"}
            },
            outputs={
                "persisted": {"type": "expression", "value": "$ctx.data.persisted"}
            },
        )
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> load"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["persisted"])  # stored:42
```

## 章へのリンク
- [第1章 · 基本コンセプト](tutorials/chapter1_foundations_ja.md)
- [第2章 · 直列フローの構築](tutorials/chapter2_linear_flow_ja.md)
- [第3章 · 分岐・ルーティング・ループ](tutorials/chapter3_routing_loops_ja.md)
- [第4章 · ファンアウト / ジョイン / 複合入力](tutorials/chapter4_fanout_joins_ja.md)
- [第5章 · 設定・テスト・運用](tutorials/chapter5_operations_ja.md)
