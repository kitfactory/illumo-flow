# Flow Tutorial

This tutorial assumes you installed the library from PyPI:

```bash
pip install illumo-flow
```

A Python REPL or script is sufficient—no repository clone is required unless you want to explore the optional examples.

## 1. Minimal Linear Flow
```python
from illumo_flow import Flow, FunctionNode

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload, ctx):
    return {**payload, "normalized": True}

def store(payload, ctx):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, name="extract", outputs="$ctx.data.raw"),
    "transform": FunctionNode(
        transform,
        name="transform",
        inputs="$ctx.data.raw",
        outputs="$ctx.data.normalized",
    ),
    "store": FunctionNode(
        store,
        name="store",
        inputs="$ctx.data.normalized",
        outputs="$ctx.data.persisted",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> store"])
context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

Flow.run は加工後の `context` を返し、各ノードの最後の出力は
`context["payloads"][node_id]` から参照できます。
```

## 2. Fail-Fast Behaviour
Raise an exception inside `transform` and rerun. The flow stops immediately, filling diagnostic keys such as `context["failed_node_id"]`, `context["failed_message"]`, and `context["errors"]`.

## 3. Dynamic Routing
```python
from illumo_flow import Flow, FunctionNode

def classify(payload, ctx):
    ctx.write("$ctx.metrics.score", 85)
    ctx.route(next="approve", confidence=90, reason="demo")

nodes = {
    "classify": FunctionNode(classify, name="classify"),
    "approve": FunctionNode(
        lambda payload, ctx: "approved",
        name="approve",
        outputs="$ctx.decisions.auto",
    ),
    "reject": FunctionNode(
        lambda payload, ctx: "rejected",
        name="reject",
        outputs="$ctx.decisions.auto",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="classify", edges=["classify >> (approve | reject)"])
ctx = {"inputs": {"application": {}}}
flow.run(ctx)
print(ctx["decisions"]["auto"])  # approved
```
If `Routing.next` is not provided, the flow follows all wired successors. `default_route` can be attached to a node when a fallback path is required.

## 4. Fan-Out and Joins
```python
from illumo_flow import Flow, FunctionNode

def seed(payload, ctx):
    return {"id": 1}

def geo(payload, ctx):
    return {"country": "JP"}

def risk(payload, ctx):
    return {"score": 0.2}

def merge(payload, ctx):
    return {"geo": payload["geo"], "risk": payload["risk"]}

nodes = {
    "seed": FunctionNode(seed, name="seed", outputs="$ctx.data.customer"),
    "geo": FunctionNode(
        geo,
        name="geo",
        inputs="$ctx.data.customer",
        outputs="$ctx.data.geo",
    ),
    "risk": FunctionNode(
        risk,
        name="risk",
        inputs="$ctx.data.customer",
        outputs="$ctx.data.risk",
    ),
    "merge": FunctionNode(
        merge,
        name="merge",
        inputs="$joins.merge",
        outputs="$ctx.data.profile",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> (geo | risk)", "(geo & risk) >> merge"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["profile"])  # {'geo': {...}, 'risk': {...}}
```
Any node with multiple incoming edges automatically waits for all parents; their outputs are exposed via `context["joins"][node_id]`.

## 5. Multiple Inputs and Outputs
```python
from illumo_flow import Flow, FunctionNode

def split(payload, ctx):
    return {"left": payload[::2], "right": payload[1::2]}

def combine(payload, ctx):
    return payload["left"] + payload["right"]

nodes = {
    "seed": FunctionNode(lambda payload, ctx: "abcdef", name="seed", outputs="$ctx.data.source"),
    "split": FunctionNode(
        split,
        name="split",
        inputs="$ctx.data.source",
        outputs={"left": "$ctx.data.left", "right": "$ctx.data.right"},
    ),
    "combine": FunctionNode(
        combine,
        name="combine",
        inputs={"left": "$ctx.data.left", "right": "$ctx.data.right"},
        outputs="$ctx.data.result",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> split", "split >> combine"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["result"])  # 'abcdef'
```

YAML example:

```yaml
flow:
  entry: seed
  nodes:
    seed:
      type: illumo_flow.core.FunctionNode
      name: seed
      context:
        inputs:
          callable: examples.ops.seed
        outputs: $ctx.data.source
    split:
      type: illumo_flow.core.FunctionNode
      name: split
      context:
        inputs:
          callable: examples.ops.split_text
          payload: $ctx.data.source
        outputs:
          left: $ctx.data.left
          right: $ctx.data.right
    combine:
      type: illumo_flow.core.FunctionNode
      name: combine
      context:
        inputs:
          callable: examples.ops.combine_text
          left: $ctx.data.left
          right: $ctx.data.right
        outputs: $ctx.data.result
  edges:
    - seed >> split
    - split >> combine
```

Load it with `Flow.from_config("flow.yaml")` to produce the same result.


## 6. Node-Managed Timeout / Retries
Encapsulate external retries within the node:
```python
import time
from illumo_flow import Flow, FunctionNode

attempts = {"count": 0}

def call_api(payload, ctx):
    attempts["count"] += 1
    if attempts["count"] < 3:
        time.sleep(0.1)
        raise RuntimeError("temporary failure")
    return {"status": 200}

nodes = {
    "call": FunctionNode(call_api, name="call", outputs="$ctx.data.api_response"),
}

flow = Flow.from_dsl(nodes=nodes, entry="call", edges=[])
ctx = {}
flow.run(ctx)
print(attempts["count"])  # 3
```
Flow remains fail-fast—retries or timeouts are entirely managed within the node implementation.

## 7. Early Stop via Routing
```python
from illumo_flow import Flow, FunctionNode

def guard(payload, ctx):
    ctx.route(next=None, confidence=100, reason="threshold exceeded")

nodes = {
    "guard": FunctionNode(guard, name="guard"),
    "downstream": FunctionNode(
        lambda payload, ctx: "should_not_run",
        name="downstream",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="guard", edges=["guard >> downstream"])
ctx = {}
flow.run(ctx)
print(ctx["steps"])  # downstream never runs
```

## 8. Optional Repository Examples
Cloning the repository gives access to the bundled CLI (`python -m examples <id>`) and pytest suite (`pytest`). These demonstrate larger flows built entirely from configuration.

## 9. Next Steps
- Reuse the patterns above to define your own callables and DSL wiring.
- Add unit tests (see `tests/test_flow_examples.py` in the repository) to protect your flows.
- Explore [docs/flow.md](flow.md) for deeper API and design details.
