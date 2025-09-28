# Flow Design Guide

## Scope
- Define how a `Flow` instance coordinates graph execution, routing, and context bookkeeping.
- Document the contracts enforced on `Node` implementations and the shared `context` dictionary.
- Enumerate scenarios that the runtime must support (serial chains, dynamic branching, fan-in/out, retries) and how each is modeled.

## Terminology
- **Flow**: Scheduler and orchestrator that owns the graph, execution queue, and runtime policies.
- **Node**: Executable unit that transforms input and contributes entries to the shared context.
- **Edge**: Declared relationship in the DSL/config showing possible successor nodes.
- **Routing Result**: `Routing` object (or list of them) emitted by a routing node, naming successor identifiers plus optional confidence/reason metadata. Payload overrides are returned separately alongside each `Routing` entry.
- **Context**: Mutable dictionary shared by all nodes for passing payloads, metadata, and diagnostics.
- **Join Target**: Node with multiple upstream edges that must receive all parent outputs before executing.

## API Reference Overview
### Flow
**Key methods**
- `__init__(*, nodes, entry, edges) -> None` — bind node instances, validate the entry, and construct adjacency/dependency maps used during execution.
- `from_dsl(*, nodes, entry, edges) -> Flow` — expand DSL edge expressions (e.g., `"A >> (B | C)"`) and return a configured `Flow`.
- `from_config(source) -> Flow` — load YAML/JSON/mapping form into the DSL structure before instantiating a `Flow`.
- `run(context=None, user_input=None) -> MutableMapping[str, Any]` — execute the graph, mutate/return the shared context, honor routing outputs, and perform join aggregation.

**Primary attributes**
- `nodes` — mapping `node_id -> Node` bound to this flow.
- `entry_id` — identifier of the entry node.
- `adjacency` / `reverse` — successor and predecessor maps (`node_id -> Set[str]`).
- `parent_counts` — number of upstream dependencies each node must satisfy.
- `parent_order` — deterministic parent ordering used when building join payloads.
- `dependency_counts` — mutable copy of parent counts consumed during a run.

### Node
**Key methods**
- `__init__(*, name, inputs=None, outputs=None, metadata=None, allow_context_access=False) -> None` — configure declarative input/output expressions and optional metadata.
- `bind(node_id: str) -> None` — attach the runtime-assigned identifier prior to execution.
- `node_id` (property) -> str — retrieve the bound node identifier (raises if unbound).
- `run(payload: Any) -> Any` — abstract method implemented by subclasses to transform the payload.
- `describe() -> Dict[str, Any]` — expose module/class/details plus normalized inputs/outputs for tooling.
- `request_context() -> MutableMapping[str, Any]` — return the shared context during execution when `allow_context_access=True`.

**Primary attributes**
- `name` — human-readable identifier used in diagnostics.
- `_inputs` / `_outputs` — normalized expression lists describing declarative inputs/outputs.
- `_allow_context_access` — flag gating direct context use.
- `_active_context` — reference to the shared context while executing (temporary, internal use only).

### Routing
**Key methods**
- `to_context() -> Dict[str, Any]` — serialize `{target, payload?, confidence?, reason?}` for persistence under `context['routing']`.

**Primary attributes**
- `target` — successor node identifier selected by a routing decision.
- `payload` — payload forwarded to the successor (optional).
- `confidence` — confidence score for the decision (optional).
- `reason` — human-readable explanation for the decision (optional).

## Core Responsibilities
### Flow
- Validate the graph at build time: orphaned nodes, missing dependencies, and cycles are rejected.
- Materialize adjacency mappings: `outgoing[node_id] -> set[edge]`, `incoming[node_id] -> set[parent_id]`.
- Schedule execution with a single `ready` queue and dependency counters, dispatching nodes once all parents complete.
- Intercept node results, honour `Routing` decisions when present, and persist the returned payload under `context["payloads"]`.
- Consolidate join payloads by storing upstream contributions in `context["joins"][join_id][parent_id]`, releasing the join once all parents report.
- Maintain fail-fast semantics (no built-in retries or global timeouts) while recording diagnostics on failure.
- Stop execution on the first exception and log diagnostics for post-mortem analysis.

- ### Node
- Implement `run(payload) -> payload`; Flow wraps the call to manage context access, record the return value, and propagate it to declared `outputs`.
- Publish metadata via `describe()` to support tooling and validation, enumerating expected context inputs/outputs so Flow can prime namespaces.
- Respect single-responsibility: one node should own one unit of work or decision boundary.
- Static transitions rely solely on DSL edges (e.g., `A >> B`). When runtime branching is required, prefer `RoutingNode` to keep regular nodes focused on payload production.
- Declare `inputs` / `outputs` (or DSL `context.inputs` / `context.outputs`) so Flow knows which context locations to read and write. Nodes only return the payload; Flow commits it to the designated paths.
- Flow primes the context with required namespaces so nodes can reference them via expressions (`$ctx.*`, `$joins.*`, etc.).
- Avoid mutating the underlying context dictionary arbitrarily; reserve writes for documented locations (e.g. metrics or outputs) so that Flow remains the single authority for shared state. Nodes that truly need shared-state access must opt in with `allow_context_access=True` and call `self.request_context()` inside `run`.
- Flow assigns graph-level node identifiers when registering the graph (typically from DSL/config keys); node instances remain identifier-agnostic so the same instance can be reused across flows.
- Every node must provide a `name`; Flow validates non-empty strings and uses them in diagnostics while keeping runtime node IDs separate for graph wiring.
- Implementations may generate private instance-scope UUIDs for metrics, but these must stay internal and never leak into routing or context keys.
- Nodes automatically wait for all upstream dependencies defined by edges; no additional declarations are required for fan-in.
- When participating in joins, return structured payloads that downstream consumers can merge without collision.
- Avoid mutating context namespaces directly; when `allow_context_access` is enabled and additional values must be exposed outside the configured outputs, confine updates to reserved keys (for example, `context.setdefault("metrics", {})`).
- `RoutingNode` subclasses implement `run(payload) -> Routing | Sequence[Routing] | Sequence[Tuple[Routing, Any]]`. Each `Routing` names a downstream `target` and optional `confidence` / `reason`; a companion payload override can be provided by returning `(Routing, payload)` tuples. Flow records the serialized list under `context["routing"]` and only enqueues the declared targets.
- `CustomRoutingNode` binds a routing-specific callable via `routing_rule` / `routing_rule_expression` and enforces `Routing` results without reusing `FunctionNode` semantics.

### Routing structure
- `Routing` fields:
  - `target`: identifier of the downstream node to execute
  - `confidence`: optional confidence score
  - `reason`: optional explanation string
- Routing nodes may return a single `Routing`, a `(Routing, payload)` tuple, or a sequence of either to express fan-out. Returning an empty sequence halts dispatch while still recording the decision. When a payload override is omitted, the original node input is forwarded.
- Flow persists the list of `{target, confidence, reason}` dictionaries to `context["routing"][node_id]` for observability and audits.

### Context
- Expose stable namespaces:
  - `context["steps"]`: ordered execution log entries `{timestamp, node_id, status, info}`.
  - `context["joins"]`: nested mapping `join_id -> parent_id -> payload` used for fan-in.
  - `context["errors"]`: stack of failure records captured whenever a node raises.
- `context["routing"]`: `node_id -> List[{target, confidence, reason}]` records produced by `RoutingNode`.
- Permit caller-defined payloads under application-specific keys while guarding reserved keys above.
- Flow initializes reserved namespaces (`context["joins"]`, etc.) before execution so nodes can operate without helper utilities.
- `context["payloads"]`: last payload emitted by each node; Flow seeds entry payloads and nodes should update their slot when producing outputs.
- Nodes may store additional outputs via configured paths (`context.output`), and reference inputs via `context.input` without manually navigating nested dictionaries.
- Shared state updates should be funneled through documented Flow mechanisms (reserved context keys or plugin hooks) rather than arbitrary dictionary mutation, mirroring platforms like n8n / Dify that strictly mediate context access.
- The transient payload passed to `Node.run` is distinct from the shared context. Flow recomputes it from `inputs` for every node and commits the return value into `context["payloads"]` and the declared `outputs`.
- Flow may read `describe()` metadata (for example, declared `context_inputs` / `context_outputs`) to pre-create or validate additional keys while keeping the public API minimal.

### Expressions (`$ctx`, `$env`, …)
- Strings that begin with `$` are treated as expressions. Supported scopes: `$ctx`, `$payload`, `$joins`, `$env`.
- Expressions inside `{{ … }}` are evaluated within strings, allowing templates such as `"Hello {{ $ctx.user.name }}"`.
- As a convenience, inputs/outputs declared as `ctx.*`, `payload.*`, or `joins.*` (without the leading `$`) are automatically normalized to the corresponding `$ctx.*` / `$payload.*` / `$joins.*` form. Similarly, the shorthand `$.path` is interpreted as `$ctx.path`. Other strings remain literals.
- Examples:
  - `$ctx.data.raw` (or `ctx.data.raw`) → `context["data"]["raw"]`
  - `$payload.extract` → `context["payloads"]["extract"]`
  - `$env.API_TOKEN` → environment variable lookup
- Pure literals that do not begin with the supported prefixes are never coerced.

## Branching Design
### Static Branching
- Derived directly from DSL edges like `A >> B` or `A >> (B | C)`.
- Flow precomputes successor sets; nodes without runtime decisions use these sets automatically.
- Validation step ensures every declared successor exists and is reachable from the entry node.

- Use `RoutingNode` when runtime decisions are required. The node returns a `Routing` instance (or sequence of instances) describing which successors to execute.
- Example:

```python
return Routing(target="approve", confidence=0.82, reason="score > 0.8"), payload
```

- Flow validates that every target matches a declared edge; unknown identifiers raise `FlowError`.
- Returning an empty list (`[]`) stops dispatch gracefully while still logging the decision.
- Multiple routes are supported—return a list of `Routing(...)` objects and optional `(Routing, payload)` tuples to fan out with per-target payloads or metadata.

## Configuration Loading
- `Flow.from_config(source)` accepts a path to a YAML/JSON file or a pre-loaded dictionary.
- Node entries support `type`, `callable`, `context.input`, `context.output`, optional `describe` metadata, and the opt-in flag `allow_context_access`.
- Example configuration:

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
        output: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        output: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        output: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

- Load and execute:

```python
from illumo_flow import Flow

flow = Flow.from_config("flow.yaml")
context = {}
flow.run(context)
```

`Flow.run` returns the mutated `context`; per-node outputs also remain under `context["payloads"]` for inspection.

`FunctionNode` instances expect the implementation path under `context.inputs.callable`. Literal strings are imported when the flow is built, while expressions (for example `$.registry.transform`) are evaluated against the runtime context. `CustomRoutingNode` follows the same pattern using `context.inputs.routing_rule` or a top-level `routing_rule` entry.

### Fan-Out and Broadcast
- For `A | B` when both edges must fire, Flow forwards the same payload object to each target without additional metadata.
- `RoutingNode` can broadcast by returning a sequence of `Routing` objects or `(Routing, payload)` tuples—each entry may carry its own payload overrides, confidence, or reason.

### Routing Implementation Guidelines
1. **Static routes**: Regular nodes return only a payload. DSL edges determine the successors in the graph definition.
2. **Runtime branching**: Use `RoutingNode` or `CustomRoutingNode` and return either a single `Routing(target=..., confidence=..., reason=...)`, a `(Routing, payload)` tuple, or a list of those for fan-out. Flow persists the decision to `context["routing"][node_id]` and schedules only the declared targets. Unknown successors trigger `FlowError`. When no payload override is supplied, the node input is forwarded.
3. **Early stop**: Return an empty list (`[]`) to halt routing gracefully. Flow logs the decision and leaves downstream nodes idle.
4. **Join targets**: Flow still aggregates payloads for join nodes under `context["joins"][target][parent]`. Payload overrides returned alongside `Routing` entries integrate seamlessly with the existing join mechanics.

### Fan-In and Joins
- Nodes with multiple incoming edges are treated as join targets automatically.
- Flow tracks pending parents via counters (`pending[(join_id)] -> remaining_count`).
- Each upstream completion stores its payload in `context["joins"][join_id][parent_id]`.
- Once the counter reaches zero, the join node is moved to the ready queue with an aggregated input payload.

### Default and Terminal Routes
- DSL wiring alone determines which successors execute; define static branches in the DSL and use `Routing` entries for dynamic selection.
- Returning an empty list from a routing node signals Flow to terminate execution gracefully after logging completion.

## Execution Lifecycle
1. Build-time compilation of DSL/config into an internal graph representation.
2. Initialization of execution state (`context` defaults, ready queue seeded with entry node).
3. Dispatch loop:
   - Pop the next node from the single `ready` queue.
   - Resolve the node payload from declared `inputs` and invoke `Node.run(payload)` (Flow temporarily attaches the shared context for nodes that opted in).
   - Handle success: log step, persist the returned payload via `outputs`, interpret any `Routing` decisions (recording them under `context["routing"]`), enqueue successors, retain recorded payloads.
   - Handle failure: capture diagnostics, mark context failure keys, abort loop.
4. Finalization: return the mutated `context`; per-node payloads remain available under `context["payloads"]`.

## State Management Structures
- Adjacency and reverse edge mappings are kept as dictionaries; dependency counters track outstanding parents.
- Join buffers are stored per target node, accumulating parent payloads until all contributors arrive.
- No dedicated helper classes are exposed—the Flow implementation relies on internal utility functions.

## Concurrency and Ordering Guarantees
- Nodes execute sequentially from the single `ready` queue; no parallel dispatch is performed.
- Ordering within a branch is preserved; joins depend on the aggregated payload assembled from parent completions.
- Nodes are responsible for their own timeout discipline; Flow observes whatever exceptions they raise.

## Error Handling Strategy
- Fail-fast default: first exception aborts the run, but Flow keeps partial context for inspection.
- Guarantee that `context["failed_node_id"]`, `context["failed_exception_type"]`, and `context["failed_message"]` are set before raising.
- For recoverable routing nodes, return an empty list (optionally with a `reason` field in the contextual log) to halt the branch gracefully without marking failure.
- Retries and timeouts are application-level concerns; nodes may implement them internally before returning control to Flow.

## Observability Requirements
- Append `{node_id, status, message?}` records to `context["steps"]` at node start, success, and failure.
- No additional tracing callbacks or metrics hooks are available yet; external instrumentation must wrap Flow externally.

## Future Roadmap Considerations
- **Extensibility hooks**: expose structured metadata from `Node.describe()` and add Flow-level pre/post execution hooks so cross-cutting concerns (logging, tracing, metrics) can be injected without patching nodes individually.
- **Error / retry policies**: keep Fail-Fast as the default while allowing optional retry/backoff modules or failure notification adapters to be registered per node or per Flow run.
- **Observability tooling**: provide first-class exporters for execution traces, step timelines, and aggregated statistics so external dashboards can introspect runs.
- **Config validation**: strengthen static checks for `context.inputs` / `context.outputs` expressions and callable declarations to catch configuration errors before execution.
- **UI readiness**: support round-trippable Flow definitions (e.g. `Flow.to_config()`), publish a node catalog with machine-readable metadata, and document expression/validation rules to power graphical editors.

### Roadmap
**Story so far**: Version 0.1.3 locks the runtime to a payload-only node contract, introduces opt-in context access (`allow_context_access`) for exceptional cases, and retains the unified YAML / DSL configuration built in 0.1.x. The next steps extend that foundation so larger projects and UI tooling can rely on predictable hooks, validation, and visibility.

**Near term (0.1.x)**
- Ship `Flow.run` context-return semantics broadly and document patterns for updating the shared context without breaking reserved namespaces.
- Implement structured metadata exports from `Node.describe()` and document a lightweight plugin interface for execution pre/post hooks.
- Harden configuration validation (expressions, callable resolution) and surface actionable errors before execution.
- Extend tests/examples to cover recommended patterns for limited context interaction (e.g., writing metrics under reserved keys) and document idiomatic usage for contributors.

**Mid term (0.2.x)**
- Introduce pluggable retry/backoff policies and failure notifiers while keeping Fail-Fast default.
- Provide tracing/metrics adapters (OpenTelemetry, JSONL) and a standardized execution report that UI/CLI can consume.
- Publish a node catalog schema (JSON) so external toolchains can enumerate available node types with inputs/outputs metadata.
- Add `Flow.to_config()` / `Flow.diff_config()` to enable round-trip editing between code and UI builders.

**Long term (0.3.x and beyond)**
- Deliver optional distributed/back-pressure runtimes while preserving the single-process default.
- Release a reference UI (or design kit) that consumes the catalog/validation schema and renders drag-and-drop workflow editors.
- Enable policy-driven observability pipelines (streaming events, durable audit logs) for enterprise deployments.
- Formalize extension points (e.g., `FlowPlugin` registry) to curate community-contributed nodes and integrations.
## Supported Scenarios Checklist
- Serial pipelines (`A >> B >> C`).
- Static fan-out (`A >> (B | C)` both active).
- Dynamic branch selection (router node chooses subset of successors at runtime).
- Parallel tasks with join (`(B & C) >> join`).
- Loop iteration via `LoopNode` with self edge (`loop >> loop`) and worker edge.
- Early termination (routing node returns an empty list to stop downstream execution).
- Timeout discipline implemented within individual nodes.

## Example Flows for Testing
- **Linear ETL chain**: `extract >> transform >> load`; validates deterministic ordering, context accumulation, and failure propagation when `transform` raises.
- **Router with confidence scoring**: `classify` returns `(Routing(target="approve", confidence=0.82, reason="score > 0.8"), payload)`; demonstrates dynamic routing with per-branch confidence and shared-context audit logging.
- **Parallel enrichment with join**: `start >> (geo | risk)` followed by `merge`; confirms parallel scheduling, join buffering in `context["joins"]`, and deterministic aggregation.
- **Node-managed timeout**: `call_api` enforces its own timeout/retry logic and raises on failure; demonstrates that Flow remains fail-fast while nodes encapsulate external resiliency.
- **Early-stop watchdog**: `guard` returns `[]` when thresholds trigger; verifies graceful termination, execution log coverage, and absence of pending tasks after stop.

## Node Implementation Checklist
- [ ] Declare human-readable `name` and metadata via `describe()`.
- [ ] Use `RoutingNode` to emit `Routing(target, confidence, reason)` entries (optionally paired with payload overrides) when runtime branching is required so per-branch metadata remains explicit。
- [ ] Bubble up exceptions; Flow logs diagnostics and fails fast (no automatic retry).
- [ ] Use `allow_context_access=True` + `self.request_context()` only when additional shared-state writes are unavoidable.
- [ ] Document required context keys in node metadata (`describe()`) so Flow can validate usage.

## Flow Implementation Checklist
- [ ] Validate graphs on construction (including unreachable nodes and duplicate ids).
- [ ] Initialize reserved context namespaces when a run starts.
- [ ] Maintain dependency counters and a single `ready` queue to schedule nodes when their parents finish.
- [ ] Persist node results under `context["payloads"]` for downstream consumption.
- [ ] Validate `RoutingNode` decisions and record them under `context["routing"]` before scheduling successors.
- [ ] Ensure join aggregation is deterministic via the stored parent order.
- [ ] Surface diagnostics on failure before raising exceptions.
- **LoopNode**: builtin helper that iterates over a sequence payload. Configure a body route (e.g. `loop >> worker`) and add a self-edge (`loop >> loop`) so it can requeue itself with the remaining items. The node emits one element per invocation (optionally `{item, index}` when `enumerate_items=True`) and returns `[]` once all elements are processed。
