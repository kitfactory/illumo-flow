# 4. RouterAgent – Choose Your Own Adventure

## You want to…
Branch the flow (“Ship or Refine?”) and know *why* the choice was made.

### Use `RouterAgent` because…
- The `choices` list ensures responses map to explicit branches.
- `output_path` / `metadata_path` automatically capture the decision and rationale.
- `ctx.routing.<id>` maintains a history of every decision for auditing.

## How to do it
1. Configure runtime (from Chapter 1).
2. Define `RouterAgent` with prompt + `choices`.
3. Bind, execute, and inspect `ctx.route` / `ctx.routing`.

```python
from illumo_flow import RouterAgent, NodeConfig

router = RouterAgent(
    config=NodeConfig(
        name="Decision",
        setting={
            "prompt": {"type": "string", "value": "Context: {{ $ctx.review }}\nAnswer with Ship or Refine."},
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

router.bind("decision")
ctx = {"review": "Tests are green and stakeholders approved."}
routing = router._execute({}, ctx)

print(routing.target, routing.reason)
print(ctx["route"]["decision"], ctx["route"]["reason"])
print(ctx["routing"]["decision"])  # historical log
```

## YAML counterpart
```yaml
flow:
  entry: decision
  nodes:
    decision:
      type: illumo_flow.nodes.RouterAgent
      context:
        inputs:
          prompt: |
            Context: {{ $ctx.review }}
            Answer with Ship or Refine.
          choices:
            - Ship
            - Refine
        output_path: $ctx.route.decision
        metadata_path: $ctx.route.reason
```
```bash
illumo run router_decision.yaml --context '{"review": "Tests are green and stakeholders approved."}'
```
- Embed the Python version when building custom orchestrations, and pass the YAML spec to `illumo run` when you want reproducible branching from the CLI.

## Detective notes
- `choices` are normalized (case-insensitive) before matching; add synonyms such as `"ship"` or `"REFINE"` and watch the router still resolve them.
- The returned object exposes `target`, `reason`, and `metadata`. The metadata keeps raw tool calls and reasoning traces, ideal for audits.
- Every router execution appends a dict with `timestamp`, `target`, and `reason` into `ctx.routing.decision`, turning the context into a decision timeline your ops team can export later.
- Combine `metadata_path` with the ConsoleTracer view to highlight why a branch fired; the tracer prints reasons in cyan by default.

## Mini quests
- Add a third choice called `Defer` that loops back to an editing node; then use Policy (Chapter 8) to retry the router when evaluation scores hover around the threshold.
- Pipe the router output into a FunctionNode that updates a dashboard via webhook—store the webhook response in `ctx.audit.router_push` to cross-reference with tracer logs.
- Swap the provider to LMStudio or Ollama and observe how the router still lines up responses, thanks to the `/v1` auto-append in the LLM loader.

## Learned in this chapter
- `RouterAgent` maps natural-language responses onto explicit branches via `choices`.
- Decisions and reasons are stored automatically with `output_path` / `metadata_path`.
- `ctx.routing` gives you a timestamped timeline of branch selections.

Next up: evaluate responses numerically with `EvaluationAgent`.
