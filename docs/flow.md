# Flow Design Guide

## Scope
- Define how a `Flow` instance coordinates graph execution, routing, and context bookkeeping.
- Document the contracts enforced on `Node` implementations and the shared `context` dictionary.
- Enumerate scenarios that the runtime must support (serial chains, dynamic branching, fan-in/out, retries) and how each is modeled.

## Terminology
- **Flow**: Scheduler and orchestrator that owns the graph, execution queue, and runtime policies.
- **Node**: Executable unit that transforms input and contributes entries to the shared context.
- **Edge**: Declared relationship in the DSL/config showing possible successor nodes.
- **Routing**: Context entry supplied by a node to tell Flow which successor edges to activate when routing is not predetermined.
- **Context**: Mutable dictionary shared by all nodes for passing payloads, metadata, and diagnostics.
- **Join Target**: Node with multiple upstream edges that must receive all parent outputs before executing.

## Core Responsibilities
### Flow
- Validate the graph at build time: orphaned nodes, missing dependencies, and cycles are rejected.
- Materialize adjacency mappings: `outgoing[node_id] -> set[edge]`, `incoming[node_id] -> set[parent_id]`.
- Schedule execution: keep three buckets (`ready`, `inflight`, `waiting_for_join`) and dispatch nodes when their prerequisites are met.
- Intercept node results, inspect updated context for routing entries, normalize them, enqueue successor runs, then clear consumed entries.
- Consolidate join payloads and unblock downstream nodes once all required parents finish.
- Enforce concurrency limits while keeping execution fail-fast (no built-in retries or global timeouts).
- Terminate early on failure, recording diagnostics for post-mortem inspection.

### Node
- Implement `run(user_input: str | None = None, context: dict) -> dict` synchronously; optional `run_async` may delegate to `run`.
- Publish metadata via `describe()` to support tooling and validation, enumerating expected context inputs/outputs so Flow can prime namespaces.
- Respect single-responsibility: one node should own one unit of work or decision boundary.
- Either set a static successor (`self.next_route`) during initialization or optionally attach a `Routing` entry to the returned context at runtime.
- Flow primes the context with required namespaces so nodes can read/write using standard dictionary semantics.
- Flow assigns graph-level node identifiers when registering the graph (typically from DSL/config keys); node instances remain identifier-agnostic so the same instance can be reused across flows.
- Implementations may generate private instance-scope UUIDs for metrics, but these must stay internal and never leak into routing or context keys.
- Nodes automatically wait for all upstream dependencies defined by edges; no additional declarations are required for fan-in.
- When participating in joins, return structured payloads that downstream consumers can merge without collision.
- Avoid mutating context namespaces not owned by the node beyond the reserved keys prepared by Flow.

### Context
- Expose stable namespaces:
  - `context["steps"]`: ordered execution log entries `{timestamp, node_id, status, info}`.
  - `context["routing"]`: decisions emitted by nodes keyed by node id.
  - `context["joins"]`: nested mapping `join_id -> parent_id -> payload` used for fan-in.
  - `context["errors"]`: stack of failure records captured whenever a node raises.
- Permit caller-defined payloads under application-specific keys while guarding reserved keys above.
- Flow initializes reserved namespaces (`context["joins"]`, `context["routing"]`, etc.) before execution so nodes can operate without helper utilities.
- Reserved location for routing decisions: `context["routing"][node_id] = Routing` using plain dictionary assignment.
- `context["payloads"]`: last payload emitted by each node; Flow seeds entry payloads and nodes should update their slot when producing outputs.
- Flow may read `describe()` metadata (for example, declared `context_inputs` / `context_outputs`) to pre-create or validate additional keys while keeping the public API minimal.

## Routing Design
### Static Routing
- Derived directly from DSL edges like `A >> B` or `A >> (B | C)`.
- Flow precomputes successor sets; nodes without runtime decisions use these sets automatically.
- Validation step ensures every declared successor exists and is reachable from the entry node.

### Dynamic Routing
- Nodes that need runtime branching store an optional `Routing` entry on the context (e.g., `context["routing"][node_id]`).
- `Routing` structure:
  ```python
  {
      "next": "B",             # successor node id, iterable of node ids, or None to stop
      "confidence": 85,         # 0-100 confidence score
      "reason": "scored branch"
  }
  ```
- Flow validates the declared `next` value(s) against allowed static successors; disallowed transitions raise routing errors.
- Stored routing entries enable reproducible routing logs and deterministic replay. Flow clears entries once they are consumed so repeated runs start from a clean state.

### Fan-Out and Broadcast
- For `A | B` when both edges must fire, Flow duplicates the outbound payload per target, tagging each with the parent node id.
- Nodes can broadcast by setting `Routing["next"]` to a collection (e.g., `["B", "C"]`).

### Fan-In and Joins
- Nodes with multiple incoming edges are treated as join targets automatically.
- Flow tracks pending parents via counters (`pending[(join_id)] -> remaining_count`).
- Each upstream completion stores its payload in `context["joins"][join_id][parent_id]`.
- Once the counter reaches zero, the join node is moved to the ready queue with an aggregated input payload.

### Default and Terminal Routes
- Nodes may define `default_route` for fallback transitions when no routing entry yields targets.
- Setting `Routing["next"] = None` (optionally with `confidence`/`reason`) signals Flow to terminate execution gracefully after logging completion.

## Execution Lifecycle
1. Build-time compilation of DSL/config into an internal graph representation.
2. Initialization of execution state (`context` defaults, ready queue seeded with entry node).
3. Dispatch loop:
   - Pop next node respecting concurrency limits.
   - Execute node (sync or async) with current context snapshot.
   - Handle success: log step, merge context delta, read any `Routing` entry from context, enqueue successors, clear the consumed entry.
   - Handle failure: capture diagnostics, mark context failure keys, abort loop.
4. Finalization: expose the last payload emitted (return value of `Flow.run`) while leaving the enriched context mutated in-place.

## State Management Structures
- `GraphIndex` data class holding adjacency lists, reverse edges, join requirements.
- `ExecutionState` encapsulating queues, in-flight counters, cancellation tokens, and other runtime metadata.
- Internal `ContextManager` component handling bookkeeping (`record_join`, `record_routing`, `push_error`) without exposing extra APIs to flow authors.
- `RouteValidator` to normalize routing entries and detect invalid transitions early.

## Concurrency and Ordering Guarantees
- Nodes without dependency conflicts can run in parallel; Flow tracks outstanding tasks per node id.
- Flow synchronizes shared context writes that could collide so user code can remain declarative.
- Ordering within a single branch is preserved; merges rely on join semantics rather than scheduler ordering.
- Nodes are responsible for their own timeout discipline; Flow observes whatever exceptions they raise.

## Error Handling Strategy
- Fail-fast default: first exception aborts the run, but Flow keeps partial context for inspection.
- Guarantee that `context["failed_node_id"]`, `context["failed_exception_type"]`, and `context["failed_message"]` are set before raising.
- For recoverable nodes, allow them to set `Routing["next"] = None` (with an explanatory `reason`) to halt gracefully without marking failure.
- Retries and timeouts are application-level concerns; nodes may implement them internally before returning control to Flow.

## Observability Requirements
- Emit structured log events for node start, completion, failure, and routing decisions.
- Optionally integrate with tracing systems—Flow should expose callbacks so instrumentations can attach spans per node.
- Maintain metrics (success count, failure count, execution latency per node) accessible via Flow hooks.

## Supported Scenarios Checklist
- Serial pipelines (`A >> B >> C`).
- Static fan-out (`A >> (B | C)` both active).
- Dynamic branch selection (router node chooses subset of successors at runtime).
- Parallel tasks with join (`(B & C) >> join`).
- Early termination (`Routing["next"] = None`).
- Timeout-induced cancellation driven by node-level logic.
- External event wait (Node defers completion by returning async awaitable handled by Flow).

## Example Flows for Testing
- **Linear ETL chain**: `extract >> transform >> load`; validates deterministic ordering, context accumulation, and failure propagation when `transform` raises.
- **Router with confidence scoring**: `classify` writes `Routing` with `next="approve"` or `"reject"`; exercises dynamic routing, auditing of `confidence`, and fallback to `default_route` when confidence is low.
- **Parallel enrichment with join**: `start >> (geo | risk)` followed by `merge`; confirms parallel scheduling, join buffering in `context["joins"]`, and deterministic aggregation.
- **Node-managed timeout**: `call_api` enforces its own timeout/retry logic and raises on failure; demonstrates that Flow remains fail-fast while nodes encapsulate external resiliency.
- **Early-stop watchdog**: `guard` places `Routing["next"] = None` when thresholds trigger; verifies graceful termination, execution log completeness, and absence of stray tasks after shutdown.

## Node Implementation Checklist
- [ ] Declare human-readable `name` and metadata via `describe()`.
- [ ] Write join and routing info into the prepared context namespaces using ordinary dict assignment.
- [ ] Return payloads under unique keys to avoid clobbering siblings.
- [ ] Store produced payloads under `context["payloads"][node_id]` so downstream nodes receive the correct input.
- [ ] Bubble up exceptions; Flow logs diagnostics and fails fast (no automatic retry).
- [ ] For async work, manage cancellation/timeout inside the node and surface exceptions promptly.
- [ ] Document required context keys in node metadata (`describe()`) so Flow can validate usage.

## Flow Implementation Checklist
- [ ] Validate graphs on construction (including unreachable nodes and duplicate ids).
- [ ] Initialize reserved context namespaces when a run starts.
- [ ] Enforce concurrency caps while leaving timeout management to node implementations.
- [ ] Normalize every routing entry read from context, log it for auditing, then clear consumed entries.
- [ ] Ensure join aggregation is atomic and deterministic.
- [ ] Surface comprehensive diagnostics on failure before raising exceptions.
- [ ] Provide extension hooks (instrumentation, custom schedulers) without leaking internals.
