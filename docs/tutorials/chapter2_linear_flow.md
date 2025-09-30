# Chapter 2 · Building a Linear Flow

We use a minimal ETL pipeline (extract → transform → load) to illustrate how to design the flow, wire nodes with the DSL, and coordinate data with the shared context before writing any code.

## 2.1 Target Flow Overview
- Accept an initial payload (user input or seed data) and let `extract` construct the domain object.
- Normalise that object in `transform` so downstream steps receive a consistent structure.
- Return the final outcome in `load`, persisting audit-friendly data into the context along the way.

This straight-through flow is the foundation you can later extend with routing, fan-out, or joins.

## 2.2 Wiring Notation and Data Movement
- Edges are described with a string DSL: `"extract >> transform"` uses `>>` to express ordering. Provide multiple edges in a list, and `Flow.from_dsl(nodes, entry, edges)` expands them into the execution graph.
- Nodes accept a payload and return the next payload. Declared `outputs` (e.g., `$ctx.data.normalized`) copy values into the shared context for observability without implicit side effects.
- Downstream nodes reference these values via `inputs="$ctx.data.raw"`, keeping the data contract explicit and aligned with the DSL wiring.

## 2.3 Design Workflow
1. Describe the node responsibilities and sequence (extract → transform → load).
2. Define the payload schema that travels between steps, including required keys and types.
3. Decide which context paths should hold results (e.g., `$ctx.data.persisted`) so instrumentation is consistent.

Capturing these decisions up front prevents churn when business rules evolve.

## 2.4 Implementation Example
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

Observe how the payload remains the only argument passed between nodes. Outputs are mirrored to the context for observability.

## 2.5 Extending the Flow Safely
- Add a new node by wiring another edge (`"load >> publish"`).
- Use configuration (YAML/dict) to capture the same structure for review.
- Keep business logic in plain functions; the Flow layer remains orchestration-only.

## Implementation & Verification Notes
- **Flow planning**: Map the linear steps and payload schema up front, and decide where to persist results (e.g., `$ctx.data.persisted`).
- **Node authoring**: Keep payloads as the only argument between nodes and mirror observability data via declared `outputs` so side effects stay explicit.
- **Result inspection**: After execution, inspect `ctx["payloads"]["load"]` or `ctx["data"]["persisted"]` to confirm the outcome aligns with business expectations.
- **Fail-fast validation**: Temporarily raise an exception inside `transform` to confirm your application reacts correctly when the flow stops early.
- **Config parity**: When you add edges in the DSL, update YAML/dict configs in lockstep so operational documentation stays accurate.
