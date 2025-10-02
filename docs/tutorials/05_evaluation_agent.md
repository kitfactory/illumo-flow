# 5. EvaluationAgent – Scoring the Output

## You want to…
Score an Agent’s output and keep both the numeric grade and the reasoning for later decisions.

### Use `EvaluationAgent` because…
- It evaluates a `target` expression, parses JSON `{score, reasons}`, and stores results in context paths automatically.
- Doing this manually with FunctionNode would mean custom parsing & bookkeeping every time.

## How to do it
1. Configure runtime (from Chapter 1).
2. Declare `EvaluationAgent` with `prompt`, `target`, and output paths.
3. Bind, execute, and inspect `ctx.metrics.*`.

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

## YAML counterpart
```yaml
flow:
  entry: review
  nodes:
    review:
      type: illumo_flow.nodes.EvaluationAgent
      context:
        inputs:
          prompt: "Provide JSON with 'score' (0-100) and 'reasons' for {{ $ctx.messages.greeting }}"
          target: $ctx.messages.greeting
        outputs: $ctx.metrics.score
        metadata_path: $ctx.metrics.reason
        structured_path: $ctx.metrics.details
```
```bash
illumo run evaluate_greeting.yaml --context '{"messages": {"greeting": "Hello world"}}'
```
- Use Python when integrating EvaluationAgent into automated pipelines; use the YAML flow for quick CLI scoring sessions or documentation.

## Why evaluators rock
- `target` expressions can reference any context slot—grade drafts, tool outputs, or full transcripts.
- JSON parsing is resilient: if the model returns plain text, EvaluationAgent still extracts numeric scores via heuristics and records the raw answer as metadata.
- ConsoleTracer tags evaluation spans in magenta, so scoring steps stand out from drafting nodes.
- Pair EvaluationAgent with Policy retries to re-grade content after automated refinements.

## Try this
- Ask the model for extra fields such as `{"score":0-100,"reasons":[],"action_items":[]}` and store `action_items` via `structured_path` for RouterAgent to consume later.
- Change `output_path` to `$ctx.metrics.history[-1].score` to maintain a rolling list of past evaluations.
- Run the evaluator twice with different prompts (user satisfaction vs. compliance) and compare how the context influences `ctx.metrics.details`.
- Route low scores to a follow-up Agent that rewrites the draft, then send the new output back into this evaluator to close the loop.

## Learned in this chapter
- `EvaluationAgent` is the go-to class for generating scores and rationales from LLMs.
- JSON is parsed automatically; fallbacks still capture useful plain-text scores.
- With scores in hand, we can build a multi-agent launch advisor in Chapter 6.
