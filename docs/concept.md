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
- Abstract `Node` defines the minimal contract for binding, metadata exposure, and execution delegation.
- Subclasses implement `run(payload) -> Any`; Flow wraps the call so it can record payloads, write configured outputs, and still expose shared context access via `self.request_context()` when special handling is unavoidable.
- `RoutingNode` (and helpers such as `CustomRoutingNode`) implement `run(payload) -> Routing | Sequence[Routing] | Sequence[Tuple[Routing, Any]]`, returning structured branch decisions instead of plain payloads.
- `run_async` reuses the synchronous semantics by delegating to `run`, keeping the default implementation simple.
- Concrete nodes may be registered via subclass discovery or explicit instantiation, enabling environment-specific extensions.
- Nodes should remain single-responsibility and composable to avoid monolithic logic.
- Each node exposes self-description via `describe() -> dict` (module, class, summary, context inputs/outputs) so tooling and loaders can present module catalogs.

-### Routing Data Model
- `Routing` captures the outcome of a routing decision for a single successor: it records the downstream `target` and optional `confidence` / `reason` annotations.
- A routing node may return one `Routing` instance, `(Routing, payload)` tuples, or a sequence of those when fan-out is required. Returning an empty sequence stops dispatch gracefully.
- Flow stores the serialized decision (list of `{target, payload, confidence, reason}`) in `context["routing"][node_id]`, enabling later inspection by operators or downstream agents.

## Error Policy
- Fail-fast philosophy: raise immediately with actionable context
- No silent recovery or retries unless explicitly modeled within the workflow
- Keep logs minimal and focused on tracing failures

## DSL Quickstart
```python
from illumo_flow import Flow, FunctionNode, NodeConfig


def start_payload(payload):
    return payload


def emit_a(payload):
    return f"A:{payload}"


def emit_b(payload):
    return f"B:{payload}"


def join_values(payload):
    return f"JOIN:{payload['A']},{payload['B']}"


MODULE = __name__

start = FunctionNode(
    config=NodeConfig(
        name="start",
        setting={"callable": {"type": "string", "value": f"{MODULE}.start_payload"}},
        outputs={"start": {"type": "expression", "value": "$ctx.data.start"}},
    )
)
A = FunctionNode(
    config=NodeConfig(
        name="A",
        setting={
            "callable": {"type": "string", "value": f"{MODULE}.emit_a"}
        },
        inputs={"payload": {"type": "expression", "value": "$ctx.data.start"}},
        outputs={"A": {"type": "expression", "value": "$ctx.data.A"}},
    )
)
B = FunctionNode(
    config=NodeConfig(
        name="B",
        setting={
            "callable": {"type": "string", "value": f"{MODULE}.emit_b"}
        },
        inputs={"payload": {"type": "expression", "value": "$ctx.data.start"}},
        outputs={"B": {"type": "expression", "value": "$ctx.data.B"}},
    )
)
join = FunctionNode(
    config=NodeConfig(
        name="join",
        setting={
            "callable": {
                "type": "string",
                "value": f"{MODULE}.join_values"
            }
        },
        inputs={"join": {"type": "expression", "value": "$joins.join"}},
        outputs={"joined": {"type": "expression", "value": "$ctx.data.join"}},
    )
)

flow = Flow.from_dsl(
    nodes={"start": start, "A": A, "B": B, "join": join},
    entry="start",
    edges=[
        "start >> (A | B)",  # fan-out
        "(A & B) >> join",   # fan-in
    ],
)

ctx = {}
flow.run(ctx, user_input=42)
print(ctx["payloads"]["join"])  # "JOIN:A:42,B:42"
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
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: start_func
        outputs: data.start
    A:
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: node_a
          payload: $ctx.data.start
        outputs: data.A
    B:
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: node_b
          payload: $ctx.data.start
        outputs: data.B
    join:
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: join_func
          payload: $joins.join
        outputs: data.join
  edges:
    - start >> (A | B)
    - (A & B) >> join
```
- Loaders resolve symbolic callables (for example `start_func`) via `context.inputs.callable` (or `context.inputs.routing_rule` for routing nodes), importing literals and evaluating expressions when required
- Parsed configs normalize into the internal dictionary that `Flow` expects, keeping code-defined and config-defined flows interoperable
- Node entries may carry metadata (`summary`, `inputs`, `returns`) that populate `node.describe()` for documentation and validation
- Custom loaders can enforce environment restrictions (allowed modules, sandbox policies) before instantiating nodes
- `context.inputs` / `context.outputs` entries define where data is read from and written to within the shared context dictionary

## Runtime Behavior
- Parallel execution: every node with satisfied dependencies starts without delay
- Router branches: `|` respects `RoutingNode` decisions (recorded under `context["routing"]`), while `&` always dispatches to all participants
- Implicit join: nodes with multiple incoming edges receive a dictionary of parent outputs (e.g. `{ "A": ..., "B": ... }`)
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

### Branching Guidelines
1. Express static transitions directly in the DSL (`A >> B`).
2. For runtime decisions, implement a `RoutingNode` and return a single `Routing(target=..., confidence=..., reason=...)`, an optional `(Routing(...), payload)` tuple, or a list of those to fan out.
3. Join targets continue to receive dictionaries via `context["joins"][target_id]`; provide per-route payloads through the tuple return when必要.
4. Return an empty list (`[]`) to stop dispatch explicitly. Supplying a `Routing` whose `target` does not exist in the DSL raises `FlowError`.

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
