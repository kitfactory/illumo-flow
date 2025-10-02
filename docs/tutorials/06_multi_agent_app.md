# 6. Multi-Agent Mini App

## Goal
Chain Agent → RouterAgent → EvaluationAgent to build a playful “launch advisor” application that decides whether to ship a feature.

## Why it’s delightful
- Agents collaborate like team members: author, reviewer, decision-maker.
- You get end-to-end context (`ctx.*`) that feels like a storyline.

## Workflow Outline
1. `AuthorAgent` drafts release notes.
2. `EvaluationAgent` scores the draft.
3. `RouterAgent` decides “Ship” or “Refine” based on the score.
4. Optional loop back to `AuthorAgent` if the score is low.

## Hands-on Flow (DSL)
```yaml
flow:
  entry: author
  nodes:
    author:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: |
            Draft release notes for {{ $ctx.feature.name }}.
        outputs: $ctx.notes.draft
    review:
      type: illumo_flow.nodes.EvaluationAgent
      context:
        inputs:
          prompt: "Return JSON {'score': 0-100, 'reasons': ...} for {{ $ctx.notes.draft }}"
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

Run from CLI:
```bash
illumo run flow_launch.yaml --context '{"feature": {"name": "Smart Summary"}}'
```

## Stretch goal: looping refinement
- If `ctx.route.decision == "Refine"`, append a YAML edge `decide >> author` with a loop guard.
- Maintain history in `ctx.history.author` to prevent endless loops.

## Checklist
- [ ] Flow produces draft notes, score, and decision.
- [ ] Context contains rationale (`ctx.route.reason`) so humans can review.
- [ ] Optional loop refinements only fire when the decision asks for it.

With the app working, let’s observe it using different tracers in Chapter 7.
