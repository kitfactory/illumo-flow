# illumo-flow

Workflow orchestration primitives featuring declarative DSL wiring, routing control, and fail-fast execution.

## Installation
```bash
pip install illumo-flow
```

## Quick Example
```python
from illumo_flow import Flow, FunctionNode

# Define lightweight callables (payload-first; shared context access is opt-in)
def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload):
    return {**payload, "normalized": True}

def load(payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, name="extract", outputs="$ctx.data.raw"),
    "transform": FunctionNode(
        transform,
        name="transform",
        inputs="$ctx.data.raw",
        outputs="$ctx.data.normalized",
    ),
    "load": FunctionNode(
        load,
        name="load",
        inputs="$ctx.data.normalized",
        outputs="$ctx.data.persisted",
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

# Flow.run returns the mutated context; per-node outputs remain
# available under `context["payloads"]`.
```

## Examples & CLI
The GitHub repository ships reference examples and a CLI (e.g. `python -m examples linear_etl`).
Clone the repo if you want to explore them locally:
```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow
python -m examples linear_etl
```

## YAML Configuration
Flows can also be defined in configuration files:

```yaml
flow:
  entry: extract
  nodes:
    extract:
      type: illumo_flow.core.FunctionNode
      name: extract
      context:
        inputs:
          callable: examples.ops.extract
        outputs: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        outputs: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        outputs: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

`context.inputs.callable` supplies the Python callable path for each node. Literal strings are imported at build time, while expressions (e.g. `$ctx.registry.my_func`) are evaluated during execution.

### Expressions
- `$ctx.*` accesses the shared context (e.g. `$ctx.data.raw`). Writing `ctx.*` or the shorthand `$.path` is automatically normalized to the same form.
- `$payload.*` reads from `context["payloads"]`
- `$joins.*` reads from `context["joins"]`
- `$env.VAR` reads environment variables
- Template strings like `"Hello {{ $ctx.user.name }}"` are supported in `inputs` definitions

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

### Payload vs Context
- Flow resolves each node's `payload` from the declared `inputs`.
- Nodes return the next `payload`; Flow stores it under `context["payloads"][node_id]` and writes to the paths declared in `outputs`.
- Treat the payload as the primary contract. Only nodes created with `allow_context_access=True` can reach the shared dictionary (e.g., for metrics via `context.setdefault("metrics", {})`); everyone else operates purely on payloads.

### Branching
- To route dynamically, return a dictionary mapping successor identifiers to payloads (e.g. `{"approve": payload}`). Only the listed successors are executed.
- Returning an empty dictionary `{}` stops downstream execution; returning multiple keys broadcasts to all corresponding successors.

## Testing (repository clone)
Keep runs short and deterministic by executing one test at a time.

- Update or extend scenarios inside `tests/test_flow_examples.py` (edit-only policy for this repo).
- Execute `pytest tests/test_flow_examples.py::TEST_NAME`; set `FLOW_DEBUG_MAX_STEPS=200` when exercising looping flows to guard against hangs.
- Track progress in `docs/test_checklist.md` and reset all checkboxes before regression sweeps.

Refer to `docs/test_checklist.md` for the live checklist.

## Documentation
- Architecture and API design: [docs/flow.md](docs/flow.md)
- Japanese version: [docs/flow_ja.md](docs/flow_ja.md)
- Concepts overview: [docs/concept.md](docs/concept.md)
- Quick tutorial reference: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)
- Chaptered tutorial (design foundations + samples): [docs/tutorials/README.md](docs/tutorials/README.md) / [docs/tutorials/README_ja.md](docs/tutorials/README_ja.md)

## Highlights
- DSL edges such as `A >> B`, `(A & B) >> C`
- Payload-first callable interface（`allow_context_access=True` を指定したノードのみ共有コンテキストへ明示アクセス）
- LoopNode for per-item iteration (self edge `loop >> loop` + body route `loop >> worker`)
- Branching via returned mappings (e.g. `{successor: payload}`)
- Built-in join handling (nodes with multiple parents automatically wait for all inputs)
- Examples covering ETL, dynamic routing, fan-out/fan-in, timeout handling, and early stop
