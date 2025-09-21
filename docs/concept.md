# Concept

## Library Intent
- Lightweight workflow runner installable via `pip`
- Emphasizes quick setup and teardown for short-lived automation
- Uses dictionaries that may embed configuration files or DSL fragments to describe flows

## Execution Model
- `Flow` orchestrates execution based on the supplied workflow dictionary
- Workflows compose `Node` subclasses chained together to express control and data movement
- Nodes can emit results or short-circuit execution; the flow exits immediately on failure

## Node Lifecycle
- Abstract `Node` defines the minimal contract for execution and context handling
- Core synchronous API: `run(user_input: str, context: dict) -> dict` returns the updated context used by downstream nodes
- `run_async` is the asynchronous counterpart that delegates to `run` for event-loop driven flows
- Concrete nodes register at startup by subclass discovery, allowing environment-specific extensions
- Nodes should remain single-responsibility and composable to avoid monolithic logic
- Every node exposes self-description via `describe() -> dict` (module name, summary, argument metadata, return payload hints) so tooling and loaders can present module catalogs

## Error Policy
- Fail-fast philosophy: raise immediately with actionable context
- No silent recovery or retries unless explicitly modeled within the workflow
- Keep logs minimal and focused on tracing failures

## DSL Quickstart
```python
from illumo import Flow, FunctionNode

start = FunctionNode(lambda ctx, x: x, name="start")
A     = FunctionNode(lambda ctx, x: f"A:{x}", name="A")
B     = FunctionNode(lambda ctx, x: f"B:{x}", name="B")
join  = FunctionNode(lambda ctx, inp: f"JOIN:{inp['A']},{inp['B']}", name="join")

flow = Flow.from_dsl(
    nodes={"start": start, "A": A, "B": B, "join": join},
    entry=start,
    edges=[
        start >> (A | B),     # fan-out
        (A & B) >> join,      # fan-in
    ],
)

ctx = {}
result = flow.run(ctx, 42)
print(result)         # "JOIN:A:42,B:42"
print(ctx["steps"])  # execution trace
```
- Sugar operators keep the flow declarative while letting nodes hide imperative behavior
- Additional nodes become available whenever subclasses are present at startup

## DSL Operators
- `A >> B` — serial: run `B` immediately after `A`
- `A | B` — choice set: routers pick one branch, regular nodes fan out to both
- `A & B` — required set: dispatch to both and express fan-in via `(A & B) >> join`

## Configuration-Driven Flows
- `Flow.from_config(path_or_dict, loader=...)` hydrates graphs from YAML/TOML/JSON definitions
- Config files reuse the same operator syntax to describe edges, for example:

```yaml
flow:
  entry: start
  nodes:
    start:
      type: illumo.nodes.FunctionNode
      callable: start_func
    A:
      type: illumo.nodes.FunctionNode
      callable: node_a
    B:
      type: illumo.nodes.FunctionNode
      callable: node_b
    join:
      type: illumo.nodes.FunctionNode
      callable: join_func
  edges:
    - start >> (A | B)
    - (A & B) >> join
```
- Loaders resolve symbolic callables (for example `start_func`) to Python objects via import strings or registries
- Parsed configs normalize into the internal dictionary that `Flow` expects, keeping code-defined and config-defined flows interoperable
- Node entries may carry metadata (`summary`, `inputs`, `returns`) that populate `node.describe()` for documentation and validation
- Custom loaders can enforce environment restrictions (allowed modules, sandbox policies) before instantiating nodes

## Runtime Behavior
- Parallel execution: every node with satisfied dependencies starts without delay
- Router branches: `|` consumes router decisions, `&` always dispatches to all participants
- Implicit join: nodes with multiple incoming edges receive a dictionary of parent outputs (e.g. `{"A": ..., "B": ...}`)
- Error handling: fail-fast—`Flow.run` raises on the first failure and records diagnostics in `ctx`

```python
try:
    flow.run(ctx, 99)
except Exception as exc:
    print("error:", exc)

print(ctx["failed_node_id"])
print(ctx["failed_exception_type"])
print(ctx["failed_message"])
print(ctx["errors"])
```

### Routing Guidelines
1. Set `self.next_routing = "B"` when the DSL wiring uniquely determines the successor (e.g., `A >> B`).
2. Omit `next_routing` if runtime logic decides the next hop; write a `RoutingInfo` instance to `context["routing"]` (or a configured key) instead.
3. Nodes with multiple parents should store their combined payload in a predictable namespace such as `context["joins"]["join_id"]`.
4. When neither `next_routing` nor context routing exists, `Flow` raises a routing error (or falls back to `default_route`) so undefined transitions stay detectable.

## Backstage Capabilities
- Pydantic-driven validation for inputs and node contracts
- Per-node timeout enforcement
- Parallelism limits
- Trace integration (e.g., OpenTelemetry, Langfuse)

## Why Flow
| Perspective | Flow | LangGraph | Mastra |
| --- | --- | --- | --- |
| Syntax | Operator DSL (`| & >>`) | Builder functions | Builder functions |
| Readability | High (ASCII operators expose wiring) | Medium | Medium |
| Serial/branch/join | 2–3 lines | 5–7 lines | 5–7 lines |
| Router expression | `router >> (A | B)` | Router function + mapping | Router + mapping |
| Join input shaping | Auto dictionary | Manual | Manual |
| Types/ops | Handled behind the scenes | Exposed at surface | Exposed at surface |

Key traits
- Concise: often half the lines of comparable frameworks
- Readable: ASCII operators visualize wiring flow
- Production-ready: validation and controls apply automatically
- Clear entrypoint: `Flow.from_dsl` anchors the DSL API
