# 6. Multi-Agent Mini App

## You want to…
Combine Agents so they draft, review, and decide on a feature release—like a playful launch advisor.

### Use this pattern because…
- `Agent`, `EvaluationAgent`, and `RouterAgent` cover authoring, scoring, and branching respectively.
- Shared context (`ctx.notes`, `ctx.metrics`, `ctx.route`) lets each step build on the previous.

## Flow outline
1. `AuthorAgent` drafts the notes.
2. `EvaluationAgent` assigns a score.
3. `RouterAgent` decides “Ship” or “Refine”.
4. Optionally loop back to `AuthorAgent` when score is low.

## Python implementation
```python
from illumo_flow import Flow, Agent, EvaluationAgent, RouterAgent, NodeConfig

author = Agent(
    config=NodeConfig(
        name="AuthorAgent",
        setting={
            "prompt": {"type": "string", "value": "Draft release notes for {{ $ctx.feature.name }}"},
            "output_path": {"type": "string", "value": "$ctx.notes.draft"},
        },
    )
)

review = EvaluationAgent(
    config=NodeConfig(
        name="ReviewAgent",
        setting={
            "prompt": {
                "type": "string",
                "value": "Return JSON {'score':0-100,'reasons':...} for {{ $ctx.notes.draft }}",
            },
            "target": {"type": "string", "value": "$ctx.notes.draft"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "metadata_path": {"type": "string", "value": "$ctx.metrics.reason"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

decide = RouterAgent(
    config=NodeConfig(
        name="RouterAgent",
        setting={
            "prompt": {
                "type": "string",
                "value": "Draft score: {{ $ctx.metrics.score }} ({{ $ctx.metrics.reason }})\nShip or Refine?",
            },
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

flow = Flow.from_dsl(
    nodes={"author": author, "review": review, "decide": decide},
    entry="author",
    edges=["author >> review", "review >> decide"],
)

context = {"feature": {"name": "Smart Summary"}}
flow.run(context)
print(context["route"]["decision"], context["route"]["reason"])
```

## YAML example
```yaml
flow:
  entry: author
  nodes:
    author:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "Draft release notes for {{ $ctx.feature.name }}"
        outputs: $ctx.notes.draft
    review:
      type: illumo_flow.nodes.EvaluationAgent
      context:
        inputs:
          prompt: "Return JSON {'score':0-100,'reasons':...} for {{ $ctx.notes.draft }}"
          target: $ctx.notes.draft
        outputs: $ctx.metrics.score
        metadata_path: $ctx.metrics.reason
        structured_path: $ctx.metrics.details
    decide:
      type: illumo_flow.nodes.RouterAgent
      context:
        inputs:
          prompt: |
            Draft score: {{ $ctx.metrics.score }} ({{ $ctx.metrics.reason }})
            Should we Ship or Refine?
        choices: [Ship, Refine]
        output_path: $ctx.route.decision
        metadata_path: $ctx.route.reason
  edges:
    - author >> review
    - review >> decide
```
```bash
illumo run flow_launch.yaml --context '{"feature": {"name": "Smart Summary"}}'
```
- Reach for the Python script when embedding the launch advisor inside a service; share the YAML flow when you want collaborators to replay it via CLI.

## Optional loop
Add `decide >> author` and guard it with a condition so only “Refine” reruns the draft.

## Narrative tips
- Store every draft iteration in `ctx.notes.versions` (append list) so EvaluationAgent can reference previous attempts when scoring.
- Use `ctx.metrics.reason` inside the author prompt to let the writer agent learn from the reviewer’s critique.
- Attach a `metadata_path` to the router to record why “Ship” won; later chapters show how Policy can fall back when the reason is “missing tests”.
- ConsoleTracer will color the author’s instruction/input/response triad differently from the reviewer and router, effectively giving your flow a color-coded comic strip.

## Stretch goals
- Introduce a second EvaluationAgent focused on compliance and average the two scores before routing.
- Chain a Policy override on the author node (e.g., retry twice with exponential backoff) so flaky provider calls do not derail the loop.
- Serialize the entire context after each run (`json.dump(ctx, open("launch_snapshot.json"))`) to build a time-lapse of decisions.

## Learned in this chapter
- You can orchestrate multiple Agent types to act like a small team.
- Context keys (`ctx.notes`, `ctx.metrics`, `ctx.route`) carry the story from draft to decision.
- Loops and RouterAgent let you adapt flows based on evaluation results.

Let’s watch this flow in action via tracers in Chapter 7.
