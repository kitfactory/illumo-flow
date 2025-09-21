# Flow Tutorial

## 1. Quick Start
- Create a virtual environment (`uv venv --seed`, then activate `.venv`).
- Install the package in editable mode: `pip install -e .`.
- Run the simplest flow example:

```bash
python -m examples linear_etl
```

You should see the final payload (`persisted`), executed steps, and node payloads recorded in the context.

## 2. Building Your First Flow (Linear ETL)
1. Inspect `examples/ops.py` and review `extract`, `transform`, `load`. Each takes `(context, payload)` and stores results under `context["outputs"]` and `context["payloads"]`.
2. Instantiate nodes and wire them:

```python
from illumo_flow import Flow, FunctionNode
from examples import ops

nodes = {
    "extract": FunctionNode(ops.extract),
    "transform": FunctionNode(ops.transform),
    "load": FunctionNode(ops.load),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
result = flow.run(context)
```

3. Verify the context: `context["payloads"]` maps node IDs to outputs and `context["steps"]` tracks ordering.
4. Inject a failure (raise in `transform`) to observe fail-fast behavior. `context["failed_node_id"]` and related keys capture diagnostics.

## 3. Branching with Routing
1. Execute the router example:

```bash
python -m examples confidence_router
```

2. The `classify` node writes a `Routing` entry (`next`, `confidence`, `reason`) to `context["routing"]["classify"]`. Flow validates targets and respects `default_route` when none selected.
3. Modify `examples/ops.classify` to force `manual_review` and rerun—notice the change in `steps` and `payloads`.

## 4. Parallel Enrichment and Joins
1. Run the fan-out/fan-in flow:

```bash
python -m examples parallel_enrichment
```

2. `seed` fans to `geo` and `risk`; because `merge` has incoming edges from both nodes, it receives the aggregated payload `{ "geo": ..., "risk": ... }` once each parent completes.
3. Inspect `context["joins"]["merge"]` to see how partial results are buffered until all parents finish.

## 5. Node-Managed Timeout and Early Stop
### Timeout Inside Nodes
- `python -m examples node_managed_timeout`
- `call_api_with_timeout` demonstrates retry/timeout logic handled inside the node. Flow remains fail-fast; `steps` shows recorded attempts.

### Early Stop via Routing
- `python -m examples early_stop_watchdog`
- `guard` emits `Routing(next=None, reason=...)`, terminating the flow gracefully before downstream execution.

## 6. Creating Your Own Flow
1. Write callable nodes with `(context, payload)` signature. Store results under `context["payloads"][node_id]` and document usage in `describe()` metadata.
2. Compose nodes in a dict.
3. Build a flow via `Flow.from_dsl` using edge strings (`"A >> B"`, `"(A & B) >> join"`) or explicit tuples. Any node with multiple incoming edges automatically waits for all parents before running.
4. Run the flow, inspect routing (`context["routing"]`), joins (`context["joins"]`), and diagnostics (`context["steps"]`, `context["errors"]`).

## 7. Next Steps
- Mirror these flows in `tests/`, similar to `tests/test_flow_examples.py`, to guard regressions.
- Integrate logging/tracing by hooking into `context["steps"]` records.
- Read `docs/flow.md` / `docs/flow_ja.md` for advanced design details (context namespaces, execution lifecycle, observability hooks).
