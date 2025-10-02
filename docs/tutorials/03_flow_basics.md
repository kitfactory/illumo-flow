# 3. Flow Fundamentals – Wiring Agents & Functions

## You want to…
Chain nodes so an Agent’s output feeds deterministic Python logic, and run the flow via CLI or code.

### Use `Flow` because…
- `Flow` (class `illumo_flow.core.Flow`) maps DSL edges to execution order and context evaluation.
- `inputs` / `outputs` expressions keep payloads and context tidy.

## How to do it
1. Define nodes (`Agent`, `FunctionNode`).
2. Build a flow with `Flow.from_dsl` or YAML.
3. Run it and inspect context outputs.

```python
from illumo_flow import Flow, FunctionNode, Agent, NodeConfig

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "prompt": {"type": "string", "value": "Draft a welcome message for {{ $ctx.user.name }}"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
        },
    )
)

def post_process(payload):
    return payload.upper()

uppercase = FunctionNode(
    config=NodeConfig(
        name="ToUpper",
        setting={"callable": {"type": "string", "value": "path.to.module.post_process"}},
        inputs={"payload": {"type": "expression", "value": "$ctx.messages.greeting"}},
        outputs="$ctx.messages.shout",
    )
)

flow = Flow.from_dsl(
    nodes={"greet": greeter, "upper": uppercase},
    entry="greet",
    edges=["greet >> upper"],
)

ctx = {"user": {"name": "Kai"}}
flow.run(ctx)
print(ctx["messages"]["shout"])
```

## CLI/YAML counterpart
```yaml
flow:
  entry: greet
  nodes:
    greet:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "Draft a welcome message for {{ $ctx.user.name }}"
        outputs: $ctx.messages.greeting
    upper:
      type: illumo_flow.core.FunctionNode
      context:
        inputs:
          callable: path.to.module.post_process
          payload: $ctx.messages.greeting
        outputs: $ctx.messages.shout
  edges:
    - greet >> upper
```
```bash
illumo run flow.yaml --context '{"user": {"name": "Kai"}}'
```

## Flow anatomy
- The DSL parser resolves `greet >> upper` into an execution graph and caches it so repeated `flow.run` calls skip rebuilding edges.
- Each node receives inputs after expression evaluation; the evaluation engine walks the context using JSONPath-like lookups, so nested keys (`$ctx.messages.greeting`) are first-class.
- When the flow ends, the tracer closes the root span and attaches the final `ctx` snapshot as metadata if the tracer supports structured payloads (SQLite and OTEL do).
- YAML flows go through the same loader as the CLI, so experimenting in code and then promoting to YAML does not change semantics.

## Power moves
- Add a second FunctionNode that sends the uppercase message to an email API; use `outputs` to store the API response and trace it in Chapter 7.
- Try chaining `RouterAgent` (Chapter 4) after `ToUpper` by adding `upper >> route`. You can then branch into different FunctionNodes based on the LLM decision.
- For large flows, store node definitions in `examples/flows/*.yaml` and load them via `illumo run`; version-controlling those specs lets teammates replay your experiments.

## Learned in this chapter
- `Flow` orchestrates node execution and context wiring.
- `inputs` / `outputs` expressions control how data moves between nodes.
- The CLI example (`illumo run flow.yaml --context {...}`) mirrors the Python API so you can debug and automate the same flow.
