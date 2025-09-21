# Flow Tutorial

This tutorial assumes you installed the library from PyPI:

```bash
pip install illumo-flow
```

A Python REPL or script is sufficient—no repository clone is required unless you want to explore the optional examples.

## 1. Minimal Linear Flow
```python
from illumo_flow import Flow, FunctionNode

def extract(ctx, _):
    return {"customer_id": 42, "source": "demo"}

def transform(ctx, payload):
    return {**payload, "normalized": True}

def store(ctx, payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, outputs="data.raw"),
    "transform": FunctionNode(transform, inputs="data.raw", outputs="data.normalized"),
    "store": FunctionNode(store, inputs="data.normalized", outputs="data.persisted"),
}

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> store"])
context = {}
result = flow.run(context)
print(result)                      # stored:42
print(context["data"]["persisted"])  # stored:42
```

## 2. Fail-Fast Behaviour
Raise an exception inside `transform` and rerun. The flow stops immediately, filling diagnostic keys such as `context["failed_node_id"]`, `context["failed_message"]`, and `context["errors"]`.

## 3. Dynamic Routing
```python
from illumo_flow import Flow, FunctionNode, Routing

def classify(ctx, payload):
    ctx.setdefault("metrics", {})["score"] = 85
    ctx["routing"]["classify"] = Routing(next="approve", confidence=90, reason="demo")

nodes = {
    "classify": FunctionNode(classify),
    "approve": FunctionNode(lambda ctx, payload: "approved", outputs="decisions.auto"),
    "reject": FunctionNode(lambda ctx, payload: "rejected", outputs="decisions.auto"),
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

def seed(ctx, _):
    return {"id": 1}

def geo(ctx, payload):
    return {"country": "JP"}

def risk(ctx, payload):
    return {"score": 0.2}

def merge(ctx, payload):
    return {"geo": payload["geo"], "risk": payload["risk"]}

nodes = {
    "seed": FunctionNode(seed, outputs="data.customer"),
    "geo": FunctionNode(geo, inputs="data.customer", outputs="data.geo"),
    "risk": FunctionNode(risk, inputs="data.customer", outputs="data.risk"),
    "merge": FunctionNode(merge, inputs="joins.merge", outputs="data.profile"),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> (geo | risk)", "(geo & risk) >> merge"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["profile"])  # {'geo': {...}, 'risk': {...}}
```
Any node with multiple incoming edges automatically waits for all parents; their outputs are exposed via `context["joins"][node_id]`.

## 5. Node-Managed Timeout / Retries
Encapsulate external retries within the node:
```python
import time
from illumo_flow import Flow, FunctionNode

attempts = {"count": 0}

def call_api(ctx, _):
    attempts["count"] += 1
    if attempts["count"] < 3:
        time.sleep(0.1)
        raise RuntimeError("temporary failure")
    return {"status": 200}

nodes = {
    "call": FunctionNode(call_api, outputs="data.api_response"),
}

flow = Flow.from_dsl(nodes=nodes, entry="call", edges=[])
ctx = {}
flow.run(ctx)
print(attempts["count"])  # 3
```
Flow remains fail-fast—retries or timeouts are entirely managed within the node implementation.

## 6. Early Stop via Routing
```python
from illumo_flow import Flow, FunctionNode, Routing

def guard(ctx, payload):
    ctx["routing"]["guard"] = Routing(next=None, reason="threshold exceeded")

nodes = {
    "guard": FunctionNode(guard),
    "downstream": FunctionNode(lambda ctx, payload: "should_not_run"),
}

flow = Flow.from_dsl(nodes=nodes, entry="guard", edges=["guard >> downstream"])
ctx = {}
flow.run(ctx)
print(ctx["steps"])  # downstream never runs
```

## 7. Optional Repository Examples
Cloning the repository gives access to the bundled CLI (`python -m examples <id>`) and pytest suite (`pytest`). These demonstrate larger flows built entirely from configuration.

## 8. Next Steps
- Reuse the patterns above to define your own callables and DSL wiring.
- Add unit tests (see `tests/test_flow_examples.py` in the repository) to protect your flows.
- Explore [docs/flow.md](flow.md) for deeper API and design details.
