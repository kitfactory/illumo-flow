# 3. Flow Fundamentals – Wiring Agents & Functions

## Goal
Assemble nodes into a directed flow so your Agent collaborates with deterministic Python logic.

## Why it’s powerful
- Sequence and branch LLM creativity with reliable code.
- DSL strings like `start >> review` make debugging and iteration enjoyable.

## Core concepts
- `Flow.from_dsl` vs `Flow.from_config` (YAML/Python dict).
- Mapping values via `$ctx.*`, `$payload`, `$joins` in `inputs`/`outputs`.
- Running flows from CLI (`illumo run flow.yaml`) and Python.

## Hands-on: Mini Flow
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
      name: Greeter
      context:
        inputs:
          prompt: "Draft a welcome message for {{ $ctx.user.name }}"
        outputs: $ctx.messages.greeting
    upper:
      type: illumo_flow.core.FunctionNode
      name: ToUpper
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

## Checklist
- [ ] Understand how `inputs` map expressions to callable parameters.
- [ ] Run the same flow via Python and CLI.
- [ ] Confirm outputs land in expected context paths.

Next stop: use RouterAgent to branch conversations intelligently.
