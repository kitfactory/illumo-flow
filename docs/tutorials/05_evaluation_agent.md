# 5. EvaluationAgent – Scoring the Output

## Goal
Score LLM outputs and capture structured feedback so you can route or report on quality metrics.

## Why it keeps things lively
- You can gamify flows (“Did we reach 80+ points?”) and adapt behavior automatically.
- JSON responses make downstream analytics simple.

## Core concepts
- `target` expression selects what to evaluate.
- Parsing structured results (JSON) vs plain-text scores.
- Storing score, reasons, and structured payload separately.

## Hands-on
```python
from illumo_flow import EvaluationAgent, NodeConfig

evaluator = EvaluationAgent(
    config=NodeConfig(
        name="Reviewer",
        setting={
            "prompt": {
                "type": "string",
                "value": "Provide JSON with 'score' (0-100) and 'reasons' for {{ $ctx.messages.greeting }}",
            },
            "target": {"type": "string", "value": "$ctx.messages.greeting"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "metadata_path": {"type": "string", "value": "$ctx.metrics.reason"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

evaluator.bind("review")
ctx = {"messages": {"greeting": "Hello world"}}
score = evaluator._execute({}, ctx)

print("score=", score)
print(ctx["metrics"]["score"], ctx["metrics"]["reason"], ctx["metrics"]["details"])
```

## Checklist
- [ ] Score is stored both in return value and `ctx.metrics.score`.
- [ ] Reasons and structured JSON live under their paths.
- [ ] `ctx.metrics.review` log (from Chapter 2) shows timestamped entries.

Time to combine Agents into a mini multi-agent app in Chapter 6.
