# 8. Policy Mastery – Fail Fast or Recover Gracefully

## Goal
Control failure behavior through `Policy(fail_fast, retry, timeout, on_error)` at global and node levels.

## Why it’s empowering
- You decide whether a hiccup stops the flow or reroutes to a recovery node.
- Declarative retries keep experiments fun without burying logic in try/except blocks.

## Core knobs
- `fail_fast`: stop the flow immediately on error (default `True`).
- `retry`: `{max_attempts, delay, mode}` for exponential or fixed backoff.
- `timeout`: string durations (`"15s"`, `"500ms"`).
- `on_error`: `stop`, `continue`, or `goto: <node_id>`.

## Hands-on
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=False,
        retry=Retry(max_attempts=2, delay="0.5s", mode="exponential"),
        timeout="10s",
        on_error=OnError(action="goto", target="fallback"),
    )
)
```

### Node override
```yaml
  nodes:
    risky:
      type: illumo_flow.core.FunctionNode
      policy:
        fail_fast: true
        retry:
          max_attempts: 1
          delay: 0
```

### Observing behavior
- With fail_fast off, the flow continues even if one node fails (track `ctx.errors`).
- When `retry` triggers, tracer logs show `node.retry` events.
- `goto` actions push alternative targets into the execution queue.

## Checklist
- [ ] Global policy takes effect when flow is run (observe tracer output).
- [ ] Node-level policy overrides global settings.
- [ ] `ctx.errors` records failure metadata for audits.

Armed with Policy, you’re ready to wrap up and plan next adventures in Chapter 9.
