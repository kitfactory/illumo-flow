# 9. Next Steps & Reference Map

## You want to…
Turn the tutorial patterns into production-ready flows and keep leveling up your team.

### Keep exploring because…
- You already built Agents that write, critique, and decide with runtime policies and tracers.
- Extending illumo-flow is a matter of wiring new nodes or swapping adapters—no rewrite required.

## Where to go from here
- **CLI automation**: wrap `illumo run` in CI pipelines for regression testing of flows.
- **Custom nodes**: implement Node subclasses (API fetchers, vector store readers) and load them via the same DSL.
- **Telemetry integration**: plug OtelTracer into Jaeger/Tempo and build dashboards for flow health.
- **Guardrails**: enrich EvaluationAgent prompts to enforce compliance, escalate with RouterAgent when content looks risky.

## Handy references
- Architecture deep dive: `docs/flow.md`
- DSL & CLI syntax: `docs/tutorials/README.md`
- Concept overview: `docs/concept.md`
- Test checklist: `docs/test_checklist.md`

## Advanced journeys
- Combine multiple flows into a portfolio by launching them from a single orchestration script; share state through Redis or a database and watch how Policies interact at scale.
- Experiment with streaming mode on providers that support it (OpenAI Response API, LMStudio) and feed partial outputs into downstream nodes.
- Design a human-in-the-loop step by routing to RouterAgent choices like `Approve`, `Revise`, `Escalate`; capture the human decision via CLI prompts or a simple web form.
- Package your nodes into a Python distribution and publish it internally so other teams can `pip install` your adapters.

## Learned in this chapter
- You now have a roadmap for scaling illumo-flow (automation, custom nodes, observability, guardrails).
- The reference docs above are your quick lookup table when building new flows.
- The Agents, Tracers, and Policies from earlier chapters stay reusable in every new project.

Thanks for crafting along—the agents, tracers, and policies are yours to orchestrate.
