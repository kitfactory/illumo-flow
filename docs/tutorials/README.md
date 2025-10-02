
# Illumo Flow Tutorial

Use this index to explore the nine-part tutorial. Every chapter highlights a user goal, the illumo-flow class to reach it, hands-on code, and key takeaways. English and Japanese versions mirror each other chapter by chapter.

Each chapter ships with paired Python and YAML examples: embed the Python snippets in applications, or run the YAML flows with `illumo run` when you want reproducible CLI scenarios.

### Developer advantages
1. **Model switching stays easy**: provider quirks such as `/v1` suffixes are normalized, so OpenAI / Anthropic / LM Studio / Ollama share the same code path.
2. **Agent flows stay under control**: a concise DSL plus explicit orchestration puts every conversational step and router decision in plain sight.
3. **Tracing takes one toggle**: swap from colorized console spans to SQLite (and soon OTEL) to debug without ad-hoc logging.
4. **Policies flip without code edits**: choose between lenient retries and strict fail-fast behaviour per environment straight from configuration.

## Chapters (English)
- [01 · Introduction & Setup](01_introduction.md) — install `illumo-flow`, configure credentials, and meet FlowRuntime.
- [02 · Agent Basics](02_agent_basics.md) — create conversational LLM nodes with history and metadata paths.
- [03 · Flow Fundamentals](03_flow_basics.md) — wire Agents and FunctionNodes via DSL/YAML/CLI.
- [04 · RouterAgent](04_router_agent.md) — branch flows with explicit choices and audit trails.
- [05 · EvaluationAgent](05_evaluation_agent.md) — score outputs with structured JSON results.
- [06 · Multi-Agent Mini App](06_multi_agent_app.md) — orchestrate authoring, review, and decision loops.
- [07 · Tracer Playground](07_tracer_playground.md) — swap Console/SQLite/OTEL tracers and read colorized spans.
- [08 · Policy Mastery](08_policy_mastery.md) — declare retry/timeout/on_error strategies.
- [09 · Next Steps](09_next_steps.md) — extend flows, integrate telemetry, and plan new guardrails.

## Chapters (日本語)
- [01 · 導入とセットアップ](01_introduction_ja.md)
- [02 · Agent 基礎](02_agent_basics_ja.md)
- [03 · Flow 基礎](03_flow_basics_ja.md)
- [04 · RouterAgent](04_router_agent_ja.md)
- [05 · EvaluationAgent](05_evaluation_agent_ja.md)
- [06 · マルチエージェントアプリ](06_multi_agent_app_ja.md)
- [07 · トレーサー道場](07_tracer_playground_ja.md)
- [08 · Policy で制御](08_policy_mastery_ja.md)
- [09 · 次のステップ](09_next_steps_ja.md)

## How to get the most out of it
1. Follow the chapters in order; each builds on the previous runtime configuration.
2. Run the provided code snippets (`pip install illumo-flow` is all you need) and adapt them to your project.
3. Use Chapter 7 and 8 to instrument and harden any flows you deploy.
4. Keep an eye on context keys (`ctx.messages`, `ctx.metrics`, `ctx.route`, `ctx.errors`) as they evolve—the tutorial teaches you how to read them like a mission log.
5. Revisit chapters with different providers (OpenAI vs. LMStudio) to experience how the `/v1` auto-append and Policy retries behave in varied environments.

## What you will master
- Building conversational Agents, Routers, and Evaluators that share context elegantly.
- Observability via Console/SQLite/OTEL tracers, including the color-coded Agent spans.
- Resilience patterns using declarative Policy settings (retry, timeout, goto).
- Multi-agent storytelling that culminates in production-ready flows you can automate.
