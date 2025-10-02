# 2. Agent Basics – “Talk to Me”

## Goal
Build your first `Agent` node that greets a user, writes the response into the flow context, and leaves a trace for later chapters.

## Why this step is exciting
- You’ll see how a single prompt turns into reusable output paths (`$ctx.messages.greeting`).
- Mixing providers is as easy as swapping `model`/`base_url`, which keeps experimentation playful.

## What you’ll learn
- Defining an `Agent` via `NodeConfig`.
- Feeding context values into prompts with template expressions.
- Inspecting results saved under `ctx.agents.<node_id>`.

## Hands-on
```python
from illumo_flow import FlowRuntime, Agent, NodeConfig

FlowRuntime.configure()  # console tracer + default policy

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "Say hello to {{ $ctx.user.name }}"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
            "history_path": {"type": "string", "value": "$ctx.history.greeting"},
        },
    )
)

greeter.bind("greeter")
ctx = {"user": {"name": "Riko"}}
response = greeter._execute({}, ctx)

print(response)
print(ctx["messages"]["greeting"])
print(ctx["history"]["greeting"])
```

## Experimentation ideas
- Switch to LMStudio:
  ```python
  FlowRuntime.configure()
  greeter = Agent(
      config=NodeConfig(
          name="LM",
          setting={
              "provider": {"type": "string", "value": "lmstudio"},
              "model": {"type": "string", "value": "openai/gpt-oss-20b"},
              "base_url": {"type": "string", "value": "http://192.168.11.16:1234"},
              "prompt": {"type": "string", "value": "Summarize the topic: {{ $ctx.topic }}"},
          },
      )
  )
  ```
- Add `metadata_path` to gather LLM reasoning or tool usage logs.

## Checklist
- [ ] Agent responds with a personalized greeting.
- [ ] `ctx.messages.greeting` stores the latest answer.
- [ ] `ctx.agents.greeter` preserves history/metadata for future chapters.

When you can make the Agent perk up with a new greeting each run, you’re ready to orchestrate full flows in Chapter 3.
