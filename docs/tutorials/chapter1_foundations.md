# Chapter 1 · Conceptual Foundations

This chapter explains the mindset behind Illumo Flow so you can reason about architecture decisions before writing any code. We start by clarifying the execution primitives—**Flow** and **Node**—and then move on to the two runtime data structures each flow manipulates: the **payload** and the **context**.

**Flow**
- The orchestration runtime that executes a graph of nodes. You construct it via `Flow.from_dsl(nodes, entry, edges)` or `Flow.from_config(...)`, then call `flow.run(context=None, user_input=None)` to execute from the entry node forward.
- During execution the runner records node outputs and routing metadata under `context['payloads']`, `context['routing']`, manages join readiness, and dispatches branch payloads automatically.

**Node**
- A unit of work derived from the `Node` base class with at least a `run(self, payload)` implementation. The return value becomes the payload for downstream nodes; concrete flavours include `FunctionNode`, `RoutingNode`, `LoopNode`, and adapters you implement.
- Nodes declare their inputs (e.g., `$ctx.xxx`, `$payload.xxx`) and outputs (e.g., `$ctx.data.cleaned`) so context writes stay explicit. Direct context mutation is opt-in via `allow_context_access=True` and should remain exceptional.

Understanding the contract between Flow and Node makes it easier to reason about how payloads and context move through a graph, so we next compare those data structures directly.

## 1.1 Payload vs Context
| Concept | Purpose | Lifecycle | Authoring guidelines |
| --- | --- | --- | --- |
| Payload | The value passed into each node (`run(payload)`); should contain just enough information for the next node | Created/returned by nodes, optionally enriched on each hop; discarded once successors finish | Keep it immutable within a node; prefer plain dicts/objects that are easy to test |
| Context | Shared audit dictionary maintained by the runtime (`context['payloads']`, `context['joins']`, etc.) | Initialised before the run; updated automatically with payload history, joins, routing metadata, and declared outputs | Treat it as read-mostly; write to it only via declared `outputs` or explicit access when `allow_context_access=True` |

**Design principles**
- Think of the payload as the contract between nodes. Every node should be able to run with only the payload and optional configuration.
- Use the context to observe flow progress (payload history, joined inputs, routing traces). Manual writes should be rare and always intentional.
- When a node must mutate shared state (e.g., metrics), enable `allow_context_access=True` and document the keys it populates.

With these foundations in mind, the remaining sections expand on the principles that keep flows maintainable.

## 1.2 Why Payload-First Matters
- **Single responsibility**: each node receives the data it needs (the payload) and returns the data for the next node. The shared context is only a ledger; avoiding implicit mutations keeps node behaviour predictable.
- **Testability**: pure functions are simpler to unit test. When a node needs the context (e.g., metrics), it must explicitly opt in via `allow_context_access=True`.
- **Isolation**: because nodes only rely on payloads, they can be executed in different environments or replayed with recorded payloads.

## 1.3 Fail-Fast Execution Model
- Illumo Flow stops at the first exception. The runtime records diagnostics under `context["errors"]`, `context["failed_node_id"]`, and `context["failed_message"]`.
- Downstream nodes never run with partial data, so your flows remain deterministic.
- For recoverable errors, build retry logic inside the node rather than catching exceptions in the flow runner.

## 1.4 Declarative Graph Wiring
- Nodes describe work; edges describe sequencing, joins, loops.
- The same node definitions can be reused across multiple flows by changing only the DSL wiring.
- Configuration files (YAML/JSON/dicts) are first-class citizens; they map 1:1 to the Python DSL.

## 1.5 Mental Model of Context
The shared context is a structured dictionary maintained by the runtime:
- `context["payloads"][node_id]` records the most recent output from a node.
- `context["joins"][node_id]` collects parent payloads when a node has multiple upstream dependencies.
- `context["routing"][node_id]` stores metadata returned by routing nodes (branches, confidence, reason).
- `context["steps"]` is the execution timeline.

Treat the context as an audit log. Your nodes should primarily communicate via payloads and declared outputs to avoid tight coupling.

## Implementation Quick Reference
- **Payload design**: Describe the payload shape before building nodes and ensure each step can run with that data alone.
- **Declared outputs**: Decide where results should land (e.g., `$ctx.data.cleaned`) and capture them through `outputs` rather than ad-hoc mutations.
- **Context access**: Only enable `allow_context_access=True` after proving the payload contract is insufficient, and document the keys you touch.
- **Fail-fast discipline**: Wrap external calls with retry helpers so unexpected exceptions still bubble up and stop the flow deterministically.
- **Error diagnostics**: Provide actionable error messages, keep exception types specific, and cover expected failure modes in tests.
- **Graph hygiene**: Pick expressive node identifiers, describe orchestration with DSL strings like `"(geo & risk) >> merge"`, and version-control configuration sources.
