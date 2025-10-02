# 1. Introduction & Setup

## You want to…
Build LLM-driven flows without wrestling with ad-hoc scripts, and understand how Agent → Tracer → Policy fit together.

### illumo-flow helps you by…
- Providing first-class Agent nodes (`illumo_flow.nodes.Agent` etc.) that handle prompts, history, and metadata.
- Letting you orchestrate everything via `Flow`, with Tracer/Policy layers for observability and resilience.
- Shipping with CLI/YAML/Python integration so you can jump between quick runs and production use.

## Why developers love it
1. **Model switching stays easy**: the runtime smooths over provider quirks so OpenAI / Anthropic / LM Studio / Ollama all run with the same code—experimental setups graduate to production without friction.
2. **Agent flows stay under control**: describe the flow in a concise DSL and orchestrate it explicitly, keeping every conversational step or router decision transparent.
3. **Tracing is one toggle away**: switch from colorized console output to persistent storage like SQLite (and OTEL next) to debug without sprinkling print statements.
4. **Policies flip with configuration**: adjust retries vs. fail-fast rules per environment, keeping development forgiving and production strict without modifying code.

## Setup: ready in minutes
1. **Install**
   ```bash
   pip install illumo-flow
   ```
   (To hack on the repo: `git clone …` → `uv pip install -e .`)
2. **Configure credentials**
   - OpenAI API key or LMStudio base URL (`http://192.168.11.16:1234`).
   - Environment variables or runtime arguments—your choice.
3. **Sanity check**
   ```bash
   pytest tests/test_flow_examples.py::test_examples_run_without_error -q
   ```
4. **Default runtime**
   ```python
   from illumo_flow import FlowRuntime, ConsoleTracer
   FlowRuntime.configure(tracer=ConsoleTracer())  # sets tracer + default policy
   ```

## Behind the scenes
- `FlowRuntime.configure` stores tracer/policy providers in a module-level registry so both CLI (`illumo run`) and ad-hoc scripts share the same defaults.
- During configure, the LLM loader preloads the provider map (OpenAI → Anthropic → Google → LMStudio → Ollama → OpenRouter) described in docs/update_requirement.md, so later chapters can switch models with a single setting.
- The `ConsoleTracer` adapter already knows how to colorize Agent instruction/input/response events, which is why you see vivid spans without writing extra logging code.
- When you call `pytest` above, the suite exercises the Flow DSL parser, YAML loader, and Tracer bridge—treat that run as a pre-flight check before trying the hands-on snippets.

## Play along
- Pretend you are launching a weekend hackathon: clone the repo, run the sanity check, and place your API keys in a `.env` file that you load before executing the samples.
- Try toggling providers by exporting `ILLUMO_DEFAULT_PROVIDER=openai` or `lmstudio` and then run the same script; later chapters show how this preference flows into `get_llm()`.
- Keep a scratchpad open: note the context keys you care about (`ctx.messages.*`, `ctx.metrics.*`, etc.) so you can trace them as we add agents, routers, and evaluators.

## What’s next
- Chapter 2: build your first `Agent`.
- Chapter 6: orchestrate a mini multi-agent “launch advisor”.
- Chapter 7-8: instrument it with Tracer + Policy.

## Key takeaways
- illumo-flow turns multi-agent ideas into explicit flows.
- You can install + configure in minutes, ready to experiment.
- Everything else in this tutorial builds on the Agent → Tracer → Policy story.
