
# Flow Tutorial (Quick Reference)

The detailed, chaptered walkthrough now lives in [`docs/tutorials`](tutorials/README.md). This short note keeps the minimal linear example for quick recall and points you to each chapter.

## Minimal Linear Flow
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

## Chapter Index
- [Chapter 1 · Conceptual Foundations](tutorials/chapter1_foundations.md)
- [Chapter 2 · Building a Linear Flow](tutorials/chapter2_linear_flow.md)
- [Chapter 3 · Branching, Routing, and Loops](tutorials/chapter3_routing_loops.md)
- [Chapter 4 · Fan-out, Joins, and Structured Inputs](tutorials/chapter4_fanout_joins.md)
- [Chapter 5 · Configuration, Testing, and Operations](tutorials/chapter5_operations.md)
