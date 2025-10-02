# 9. Next Steps & Reference Map

## Celebrate what you built
- Prompt-driven Agents that write, critique, and decide.
- A multi-agent launch advisor with routed decisions and evaluation scores.
- Full observability via Console/SQLite/OTEL tracers.
- Declarative resilience using Policy retries and goto fallbacks.

## Where to go from here
- **CLI automation**: wrap `illumo run` in CI pipelines for regression testing of flows.
- **Custom nodes**: implement your own Node subclasses (e.g., API fetchers, vector store readers) and wire them into the same DSL.
- **Telemetry integration**: plug OtelTracer into Jaeger/Tempo and build dashboards that show flow health.
- **Guardrails**: enrich EvaluationAgent prompts to enforce compliance, escalate via RouterAgent when risky content appears.

## Useful references
- Architecture deep dive: `docs/flow.md`
- DSL & CLI syntax: `docs/tutorials/README.md`
- Concept overview: `docs/concept.md`
- Test checklist for regression: `docs/test_checklist.md`

## Sharing the fun
- Try converting this tutorial into a “feature readiness” tool for your team.
- Remix the Agents (e.g., brainstorming ➜ evaluation ➜ routing) and share lessons learned.

Thanks for crafting along—the agents, tracers, and policies are yours to orchestrate.
