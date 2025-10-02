# 2. Agent Basics – “Talk to Me”

## You want to…
Generate a personalized response with an LLM node and keep the output plus history neatly in context.

### Use `Agent` because…
- `Agent` (class `illumo_flow.nodes.Agent`) handles prompts, history, metadata slots for you.
- Alternative: FunctionNode, but you’d lose automatic context storage.

## How to do it
1. Configure runtime (Tracer + default Policy).
2. Define `Agent` via `NodeConfig` with `prompt`, `output_path`, etc.
3. Bind and execute it, inspecting `ctx.messages` and `ctx.agents.<id>`.

```python
from illumo_flow import FlowRuntime, Agent, NodeConfig

FlowRuntime.configure()

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "Say hello to {{ $ctx.user.name }}"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
            "history_path": {"type": "string", "value": "$ctx.history.greeter"},
        },
    )
)

greeter.bind("greeter")
ctx = {"user": {"name": "Riko"}}
response = greeter._execute({}, ctx)

print(response)
print(ctx["messages"]["greeting"])
print(ctx["history"]["greeter"])
```

## YAML counterpart
```yaml
flow:
  entry: greet
  nodes:
    greet:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          model: gpt-4.1-nano
          prompt: "Say hello to {{ $ctx.user.name }}"
        outputs: $ctx.messages.greeting
        history_path: $ctx.history.greeter
        metadata_path: $ctx.history.greeter_metadata
```
```bash
illumo run agent_greet.yaml --context '{"user": {"name": "Riko"}}'
```
- Reach for the Python snippet when embedding an Agent inside application code; use the YAML flow when you want teammates to run the same step via CLI.

## Playful variations
- Swap provider to LMStudio by setting `provider`, `model`, and `base_url`.
- Add `metadata_path` to capture reasoning/tool output.
- Specify `structured_path` if you expect JSON tools output so later nodes can parse it without regex gymnastics.

## Under the hood
- The agent calls `get_llm()` with the merged provider/model/base_url data; the loader appends `/v1` automatically when the endpoint is LMStudio, Ollama, or another OpenAI-compatible runtime.
- Messages are stored twice: in the explicit `history_path` you set, and inside the default bucket `ctx["agents"]["greeter"]` with keys `history`, `response`, and `metadata` for quick inspection.
- The tracer emits three colorized events—`instruction`, `input`, `response`—for every agent run, which makes multi-agent debugging far less painful.
- If you omit `output_path`, the response still lands in `ctx.agents.greeter.response`, so downstream nodes can pull from there; explicit paths simply mirror or relocate that data.

## Challenge yourself
- Replace the literal prompt with a `prompt_path` pointing to `$ctx.prompts.greeting` and populate it at runtime; this mimics how YAML flows inject dynamic prompts.
- Ask the same agent to produce both a greeting and a fun fact by returning JSON and storing it via `structured_path`; watch how EvaluationAgent consumes that structure in Chapter 5.
- Capture the execution metadata (`ctx.agents.greeter.metadata`) and print it with the tracer log to see how provider latencies and token usage surface.

## Learned in this chapter
- `Agent` is the go-to class for conversational LLM steps with automatic context storage.
- You can parameterize prompts via `{{ $ctx.* }}` expressions and capture history/metadata.
- Providers (OpenAI/LMStudio) are interchangeable with a couple of settings.
