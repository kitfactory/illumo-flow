# Chapter 3 · Branching, Routing, and Loops

Before diving into code, we outline how routing decisions propagate through a flow and how loop nodes schedule repeated work.

## 3.1 Routing Components and Responsibilities
- **RoutingNode**: A specialised node that delegates to `routing_rule(payload)` and expects one or more `Routing` objects (optionally paired with payload overrides) in return. Its responsibility is to evaluate decision logic and describe the chosen successors without executing them directly.
- **Routing**: Describes a single downstream execution (`target`) with optional `confidence` / `reason` metadata. When a different payload should be forwarded, return `(Routing(...), payload)` instead of the `Routing` alone.

These abstractions separate decision description from graph wiring so that flows remain declarative and easy to audit. Instead of returning imperative control flow, the routing rule emits explicit `Routing` records describing each chosen successor.

- Instantiate `RoutingNode(..., routing_rule=callable)` where `callable(payload)` returns either a single `Routing`, a `(Routing, payload)` tuple, or a sequence of those. Each `Routing.target` must match the branch names declared in the DSL (e.g., `approve`, `review`).
- The conditional logic itself lives inside the `routing_rule`; `Routing` simply captures the outcome **as data** so the runtime can schedule downstream nodes.
- Flow stores the list of `route.to_context()` dictionaries under `context['routing'][node_id]`, allowing downstream systems to audit decisions.
- Returning an empty list signals an intentional early exit while still logging the decision context.

> ✅ **Key idea**: The `routing_rule` decides *which* branch should fire; each `Routing(target=...)` records that decision explicitly. Only the selected targets appear in the returned list—the conditions themselves do not. Returning multiple entries fans out work to several successors in the same step.

## 3.3 Sample Flow Objectives
The running example models an approval decision with two possible outcomes:
- Route payloads with scores ≥ 0.8 to the `approve` branch and record the automated decision.
- Send lower scores to a `review` branch that marks the case for manual inspection.
- Persist the selected branch, confidence score, and reasoning in the context for future audits.

### How branches relate to conditional logic
- Each `Routing.target` corresponds to an execution path, conceptually similar to the destination you would select with `if/elif/else` statements.
- A traditional snippet like `if score >= 0.8: goto approve else: goto review` produces the same behaviour, but here the decision is represented as data rather than imperative control flow.
- Optional `confidence` / `reason` fields let you attach rich metadata that would otherwise be scattered across conditionals. Combined with DSL wiring, this keeps decision logic declarative and audit-friendly.

With the responsibilities and interfaces clarified, we can look at the implementation that realises this behaviour.

## 3.4 Routing Example
```python
from illumo_flow import Flow, CustomRoutingNode, Routing, FunctionNode, NodeConfig

def classify(payload):
    score = payload.get("score", 0.85)
    if score >= 0.8:
        branch_key = "approve"
        reason = "score>=0.8"
    else:
        branch_key = "review"
        reason = "score<0.8"

    decision_payload = {**payload, "decision": branch_key}
    return Routing(
        target=branch_key,
        confidence=score,
        reason=reason,
    ), decision_payload



def approve(payload):
    return "approved"


def review(payload):
    return "pending"

MODULE = __name__


def routing_node(name, rule_path):
    return CustomRoutingNode(
        config=NodeConfig(
            name=name,
            setting={"routing_rule": {"type": "string", "value": rule_path}},
        )
    )


def fn_node(name, func_path, *, outputs):
    return FunctionNode(
        config=NodeConfig(
            name=name,
            setting={"callable": {"type": "string", "value": func_path}},
            outputs=outputs,
        )
    )


nodes = {
    "classify": routing_node("classify", f"{MODULE}.classify"),
    "approve": fn_node(
        "approve",
        f"{MODULE}.approve",
        outputs={"auto": {"type": "expression", "value": "$ctx.decisions.auto"}},
    ),
    "review": fn_node(
        "review",
        f"{MODULE}.review",
        outputs={"manual": {"type": "expression", "value": "$ctx.decisions.manual"}},
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="classify", edges=["classify >> (approve | review)"])
ctx = {}
flow.run(ctx, user_input={"score": 0.92})
```

Inspect `context['routing']['classify']` to verify which branch executed and the metadata captured for auditing. Flow executes only the targets declared in these entries.

## 3.5 Loop Execution Model
- `LoopNode` consumes an iterable payload, dispatches each item to a body node, and enqueues itself again until the iterable is exhausted.
- With `enumerate_items=True`, the worker receives structures such as `{"item": value, "index": i}`; this is handy for logging or deduplication.
- Because loop bodies may run multiple times, keep them idempotent and document any shared context keys you touch via `request_context()`.

## 3.6 Loop Example
```python
from illumo_flow import Flow, FunctionNode, LoopNode, NodeConfig

def collect(payload, context):
    context.setdefault("results", []).append(payload)
    return payload

def finalize(payload, context):
    return f"Processed {len(context.get('results', []))} items"

def loop_node(name, *, body_route, enumerate_items=False):
    setting = {"body_route": {"type": "string", "value": body_route}}
    if enumerate_items:
        setting["enumerate_items"] = {"type": "bool", "value": True}
    return LoopNode(config=NodeConfig(name=name, setting=setting))


def fn_node(name, func_path, *, outputs=None):
    setting = {"callable": {"type": "string", "value": func_path}}
    return FunctionNode(
        config=NodeConfig(name=name, setting=setting, outputs=outputs)
    )


nodes = {
    "loop": loop_node(name="loop", body_route="worker", enumerate_items=True),
    "worker": fn_node(name="worker", func_path=f"{MODULE}.collect"),
    "report": fn_node(
        name="report",
        func_path=f"{MODULE}.finalize",
        outputs={"message": {"type": "expression", "value": "$ctx.summary.message"}},
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="loop",
    edges=["loop >> worker", "loop >> loop", "worker >> report"],
)
ctx = {}
flow.run(ctx, user_input=["a", "b", "c"])
```

- The loop node consumes `user_input` and passes each `{ "item": value, "index": i }` to the worker.
- The worker appends to `context['results']`, leaving a record of processed items. When the sequence is exhausted the loop returns `[]`, so no further iterations are scheduled.
- The `report` node runs after every worker invocation here; to trigger it only once after the loop completes, create a separate node that depends on both the loop node (triggered after completion) and explicit DSL wiring without the self-edge. Example: add a `loop_done` node wired via `loop >> loop_done` (without `loop >> loop`) so it receives control only when the loop stops.

## Implementation & Verification Notes
- **Branch design**: Establish decision criteria, branch names, and successor nodes ahead of time; agree on the audit metadata captured in each `Routing` entry.
- **Routing review**: After execution, inspect `context['routing'][node_id]` to ensure the selected branch and `confidence`/`reason` values align with business rules.
- **Early exit**: Return an empty list whenever a guard condition fails, and confirm downstream nodes remain idle as intended.
- **Loop planning**: Decide whether the worker needs indices or raw items and keep the body node idempotent when mutating shared state.
- **Loop verification**: Use context artefacts (`context['results']`, `context['steps']`) to confirm the loop iterated the expected number of times and produced the right outputs.
