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
def extract(ctx, _):
    return {"customer_id": 42, "source": "demo"}

def transform(ctx, payload):
    return {**payload, "normalized": True}

def load(ctx, payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, outputs="data.raw"),
    "transform": FunctionNode(transform, inputs="data.raw", outputs="data.normalized"),
    "load": FunctionNode(load, inputs="data.normalized", outputs="data.persisted"),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
result = flow.run(context)
print(result)                 # stored:42
print(context["data"]["persisted"])  # stored:42
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
      callable: examples.ops.extract
      context:
        outputs: data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.transform
      context:
        inputs: data.raw
        outputs: data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.load
      context:
        inputs: data.normalized
        outputs: data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

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
- `(context, payload)` callable interface with configurable context paths
- Routing metadata via `Routing(next, confidence, reason)`
- Built-in join handling (nodes with multiple parents automatically wait for all inputs)
- Examples covering ETL, dynamic routing, fan-out/fan-in, timeout handling, and early stop
