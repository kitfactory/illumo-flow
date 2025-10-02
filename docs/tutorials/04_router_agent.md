# 4. RouterAgent – Choose Your Own Adventure

## Goal
Use `RouterAgent` to steer the flow toward different branches and capture the rationale for each decision.

## Why it’s fun
- Conditional logic becomes natural language driven (“Ship or Refine?” feels like a conversation).
- You can log the agent’s reasoning to audit how choices were made.

## Core concepts
- `choices` array and how responses are matched.
- `output_path` and `metadata_path` for storing decisions.
- Reading `ctx.routing.<node_id>` for historical branch selections.

## Hands-on
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

## Checklist
- [ ] `routing.target` is always one of the configured choices.
- [ ] Decision and rationale are persisted under `ctx.route`.
- [ ] `ctx.routing.decision` accumulates every call (timestamped).

With routing mastered, we can evaluate outputs numerically in Chapter 5.
