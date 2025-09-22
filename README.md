# illumo-flow

Workflow orchestration primitives featuring declarative DSL wiring, routing control, and fail-fast execution.

## Installation
```bash
pip install illumo-flow
```

## Quick Example
```python
from illumo_flow import Flow, FunctionNode

# Define lightweight callables (each works on a shared context dict)
def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload, ctx):
    return {**payload, "normalized": True}

def load(payload, ctx):
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

# Flow.run now returns the mutated context; per-node outputs also remain
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
- Within a node, use the context view helpers (`ctx.get(...)`, `ctx.write(...)`, `ctx.route(...)`) when shared state needs to be read or updated. Direct mutation of the underlying dictionary is discouraged.

## Testing (repository clone)
```bash
pytest
```
The suite in `tests/test_flow_examples.py` validates the sample DSL flows using the `src` layout configured in `pyproject.toml`.

## Documentation
- Architecture and API design: [docs/flow.md](docs/flow.md)
- Japanese version: [docs/flow_ja.md](docs/flow_ja.md)
- Concepts overview: [docs/concept.md](docs/concept.md)
- Step-by-step tutorial: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)

## Highlights
- DSL edges such as `A >> B`, `(A & B) >> C`
- Payload-first callable interface with a constrained context view helper
- Routing metadata via `Routing(next, confidence, reason)`
- Built-in join handling (nodes with multiple parents automatically wait for all inputs)
- Examples covering ETL, dynamic routing, fan-out/fan-in, timeout handling, and early stop
