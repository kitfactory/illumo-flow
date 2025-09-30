# Chapter 4 · Fan-out, Joins, and Structured Inputs

Flows often need to split work across multiple nodes and later recombine the results. This chapter clarifies how Illumo Flow models fan-out/fan-in patterns and highlights the DSL features that support them before walking through a concrete example.

## 4.1 Fan-out Mechanics
- **Execution model**: When the DSL contains `A >> (B | C)`, the runtime forwards the current payload to each declared successor (`B`, `C`). No additional routing metadata is required; the edges themselves encode the static fan-out.
- **Join buffers**: Nodes with multiple upstream edges automatically receive a join dictionary. Flow stores each parent payload under `context["joins"][target][parent_id]` until all parents finish.
- **Parent order**: The runtime records deterministic parent order (`Flow.parent_order`) so downstream processing is stable even when parents finish out of order.
- **Shared context**: While each node can write to `context["payloads"]`, branch-specific outputs are typically written to distinct context paths (e.g., `$ctx.data.geo`).

## 4.2 Design Checklist
1. Identify the shared seed payload that must be duplicated across branches.
2. Decide what each branch produces and how it should be stored (context path, structure, validation rules).
3. Define a merge contract: determine the join node ID, how it will interpret `context["joins"][join_id]`, and what final output it should emit.
4. Consider instrumentation—recording intermediate results under `$ctx.data.*` often simplifies debugging and tests.

## 4.3 Sample Flow: Geo/Risk Enrichment
The following flow duplicates a seed payload to two enrichment nodes (`geo`, `risk`), then recombines their outputs in a `merge` node. The code demonstrates how the DSL expresses parallel branches and how the join node accesses the aggregated payload.

```python
from illumo_flow import Flow, FunctionNode, NodeConfig

def seed(payload):
    return {"id": 1}

def geo(payload):
    return {"country": "JP"}

def risk(payload):
    return {"score": 0.2}

def merge(inputs):
    return {"geo": inputs["geo"], "risk": inputs["risk"]}

MODULE = __name__

def fn_node(name, func_path, *, inputs=None, outputs=None):
    return FunctionNode(
        config=NodeConfig(
            name=name,
            setting={"callable": {"type": "string", "value": func_path}},
            inputs=inputs,
            outputs=outputs,
        )
    )


nodes = {
    "seed": fn_node(
        "seed",
        f"{MODULE}.seed",
        outputs={"customer": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "geo": fn_node(
        "geo",
        f"{MODULE}.geo",
        inputs={"payload": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "risk": fn_node(
        "risk",
        f"{MODULE}.risk",
        inputs={"payload": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "merge": fn_node(
        "merge",
        f"{MODULE}.merge",
        inputs={"joined": {"type": "expression", "value": "$joins.merge"}},
        outputs={"profile": {"type": "expression", "value": "$ctx.data.profile"}},
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="seed",
    edges=["seed >> (geo | risk)", "(geo & risk) >> merge"],
)

ctx = {}
flow.run(ctx)
```

After execution:
- `context["joins"]["merge"]` is `{ "geo": {"country": "JP"}, "risk": {"score": 0.2} }`.
- `context["data"]["profile"]` holds the merged structure emitted by the join node.

## 4.4 Structured Inputs and Outputs
- Inputs can be declared as a mapping of aliases to expressions. Flow resolves each expression and passes a dictionary to the node, improving readability when multiple context values are required.
- Outputs can likewise be a mapping, allowing a node to populate multiple context paths in one step without manual context mutation.

```python
def split_ranges(payload):
    return {"left": payload[::2], "right": payload[1::2]}

split_config = FunctionNode(
    config=NodeConfig(
        name="split",
        setting={
            "callable": {
                "type": "string",
                "value": f"{MODULE}.split_ranges",
            }
        },
        inputs={"source": {"type": "expression", "value": "$ctx.data.source"}},
        outputs={
            "left": {"type": "expression", "value": "$ctx.data.left"},
            "right": {"type": "expression", "value": "$ctx.data.right"},
        },
    )
)
```

## 4.5 Testing Fan-in Logic
- Assert that `context["joins"][join_id]` matches the expected dictionary, paying attention to parent IDs.
- Check that the final merged payload is stored in the agreed context path (e.g., `$ctx.data.profile`).
- Use deterministic seed data so the same results can be re-run during regression tests.
- When join order matters, consult `Flow.parent_order[join_id]` to ensure tests cover the intended sequencing.

## Implementation & Verification Notes
- **Design the split**: Document which branches run in parallel, the seed payload they consume, and where each branch writes its output (`$ctx.data.geo`, `$ctx.data.risk`, etc.).
- **Merge contract**: Verify that the join node reads from `$joins.<node_id>` and emits a normalized structure (e.g., `$ctx.data.profile`).
- **Structured I/O**: Prefer declarative `inputs` / `outputs` mappings so branches and join nodes remain pure functions without manual context mutations.
- **Testing strategy**: Inspect both the join buffer (`context["joins"][join_id]`) and the final merged payload, using deterministic payloads to keep assertions straightforward.
