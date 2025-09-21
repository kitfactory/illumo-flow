# illumo-flow

Workflow orchestration primitives featuring declarative DSL wiring, routing control, and fail-fast execution.

## Features
- `Flow` orchestrator with DSL edges (`A >> B`, `(A & B) >> C`)
- `Node` / `FunctionNode` abstractions using `(context, payload)` signature
- Context namespaces for steps, routing decisions, join buffers, and payloads
- Routing metadata via `Routing(next, confidence, reason)`
- Examples and smoke tests covering ETL, dynamic routing, fan-out/fan-in, timeout handling, and early stop

## Getting Started
```bash
uv venv --seed
source .venv/bin/activate
pip install -e .
```

### Run Sample Flows
Use the CLI to execute the bundled examples:
```bash
python -m examples linear_etl
python -m examples confidence_router
python -m examples parallel_enrichment
python -m examples node_managed_timeout
python -m examples early_stop_watchdog
```

### Learn by Tutorial
Follow the step-by-step guide in [docs/tutorial.md](docs/tutorial.md) (or [docs/tutorial_ja.md](docs/tutorial_ja.md)) to build flows, manage routing, and understand context contracts.

## Testing
```bash
pytest
```
The test suite leverages `tests/test_flow_examples.py`, validating all example DSL definitions using the `src` package layout configured in `pyproject.toml`.

## Documentation
- Architecture and API design: [docs/flow.md](docs/flow.md)
- Japanese version: [docs/flow_ja.md](docs/flow_ja.md)
- Concepts overview: [docs/concept.md](docs/concept.md)

## Examples
- Source code: [examples/ops.py](examples/ops.py)
- DSL definitions and CLI: [examples/sample_flows.py](examples/sample_flows.py), [python -m examples](examples/__main__.py)
