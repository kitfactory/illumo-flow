# 8. Policy Mastery – Fail Fast or Recover Gracefully

## You want to…
Keep flows resilient without wrapping every node in manual try/except blocks.

### Use `Policy` because…
- It lets you choose between fail-fast and graceful recovery with declarative settings.
- Simple retry/timeout/on_error options cover the common “retry twice, then go to fallback” patterns used by tools like n8n or Prefect.

## Core knobs
- `fail_fast`: stop the flow immediately on error (default `True`).
- `retry`: `{max_attempts, delay, mode}` for fixed or exponential backoff.
- `timeout`: string durations (`"15s"`, `"500ms"`).
- `on_error`: `stop`, `continue`, or `goto: <node_id>`.

## How to do it
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=False,
        retry=Retry(max_attempts=2, delay=0.5, mode="fixed"),
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

## YAML counterpart (global + node)
```yaml
flow:
  entry: risky
  policy:
    fail_fast: false
    timeout: 10s
    retry:
      max_attempts: 2
      delay: 0.5
      mode: fixed
    on_error:
      action: goto
      target: fallback
  nodes:
    risky:
      type: illumo_flow.core.FunctionNode
      policy:
        fail_fast: true
        retry:
          max_attempts: 1
          delay: 0
    fallback:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "Let the operator know the flow used fallback for {{ $ctx.input }}"
        outputs: $ctx.messages.fallback
```
```bash
illumo run policy_demo.yaml --context '{"input": "payload"}'
```
- Embed the Python setup when wiring policies programmatically, and keep the YAML version handy for CLI operators who need to tweak retries without touching code.

### Observe the behavior
- With `fail_fast=False`, the flow records errors in `ctx.errors` and keeps running.
- When retry triggers, ConsoleTracer shows `node.retry` events so you know it happened.
- `goto` pushes the fallback node into the queue, giving you a clean recovery path.

## Policy recipes
- **Experiment mode**: `fail_fast=False`, `retry=Retry(max_attempts=3, delay=0.2, mode="exponential")`, `on_error=OnError(action="continue")` to keep the flow running while you collect telemetry.
- **Production launch**: `fail_fast=True`, minimal retries, and `on_error=OnError(action="goto", target="support_escalation")` so failures head straight to a notification node.
- **Safety net**: combine `timeout="5s"` with a RouterAgent fallback that asks a human reviewer to step in when evaluations take too long.

## Deep dive
- Policies are merged in the order: global runtime → flow/CLI override → node-specific override. The last one wins for each attribute.
- Timeouts are parsed via `illumo_flow.policy.duration.parse_duration`, which accepts `s/ms` suffixes; invalid strings raise immediately, keeping configuration errors obvious.
- Retry metadata is stored in `ctx.errors[<node_id>]['retries']`, giving you a history of attempts for auditing.
- Policies also emit tracer events (`flow.policy.apply`, `node.retry`) that you can route to OTEL dashboards.

## Learned in this chapter
- Policy settings apply globally via `FlowRuntime.configure` and can be overridden per node.
- Retry/timeout/on_error cover the essential recovery recipes without extra code.
- With resilience configured, we can wrap up the tutorial in Chapter 9.
