# illumo-flow

Workflow orchestration primitives featuring declarative DSL wiring, routing control, and fail-fast execution.

## Why developers pick illumo-flow
1. **Easily switch language models**: the runtime absorbs provider differences so OpenAI / Anthropic / LM Studio / Ollama all run with the same code—no need to worry about `/v1` suffixes or other quirks when moving from experiments to production.
2. **Design and control agent flows with ease**: describe flows in a concise DSL, execute them through the orchestrator, and keep every conversational step or router decision under explicit control.
3. **Trace and debug effortlessly**: toggle between colorized console logs and persistent storage like SQLite (with OTEL exporters next) to retire print-based debugging once and for all。
4. **Flip execution policies on demand**: configure retries vs. fail-fast behavior per environment, so development stays forgiving while production remains strict—without touching your code.

### Tracing quickstart
```python
from illumo_flow import FlowRuntime, SQLiteTracer

FlowRuntime.configure(
    tracer=SQLiteTracer(db_path="illumo_trace.db"),
)
```

Forward spans to Tempo or any OTLP-compatible collector by wiring `OtelTracer` with a Tempo backend:

```python
from illumo_flow import FlowRuntime, OtelTracer
FlowRuntime.configure(
    tracer=OtelTracer(exporter=my_otlp_exporter),
)
```

CLI equivalent commands:

```bash
illumo run flow.yaml --context @context.json --tracer sqlite --trace-db illumo_trace.db
illumo run flow.yaml --context @context.json --tracer otel --service-name demo-service
```

`ConsoleTracer` is ideal for ad-hoc debugging, while SQLite / Tempo backends preserve history for dashboards./ConsoleTracer は即時デバッグ向け、SQLite / Tempo バックエンドは履歴保存やダッシュボード連携に適しています。


### Trace querying example
```python
from illumo_flow.tracing_db import SQLiteTraceReader

reader = SQLiteTraceReader('illumo_trace.db')
for span in reader.spans(kind='node', limit=5):
    print(span.name, span.status)
```

## Installation
```bash
pip install illumo-flow
```

## Quick Example
```python
from illumo_flow import Flow, FunctionNode, NodeConfig

# Define lightweight callables (payload-first; shared context access is opt-in)
def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload):
    return {**payload, "normalized": True}

def load(payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(
        config=NodeConfig(
            name="extract",
            setting={"callable": {"type": "string", "value": f"{__name__}.extract"}},
            outputs={"raw": {"type": "expression", "value": "$ctx.data.raw"}},
        )
    ),
    "transform": FunctionNode(
        config=NodeConfig(
            name="transform",
            setting={"callable": {"type": "string", "value": f"{__name__}.transform"}},
            inputs={"payload": {"type": "expression", "value": "$ctx.data.raw"}},
            outputs={
                "normalized": {"type": "expression", "value": "$ctx.data.normalized"}
            },
        )
    ),
    "load": FunctionNode(
        config=NodeConfig(
            name="load",
            setting={"callable": {"type": "string", "value": f"{__name__}.load"}},
            inputs={
                "payload": {"type": "expression", "value": "$ctx.data.normalized"}
            },
            outputs={
                "persisted": {"type": "expression", "value": "$ctx.data.persisted"}
            },
        )
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

# Flow.run returns the mutated context; per-node outputs remain
# available under `context["payloads"]`.
```

## Examples & CLI
The repository ships runnable flows and a CLI:

```bash
# Execute a YAML flow with JSON context
illumo run examples/multi_agent/chat_bot/chatbot_flow.yaml --context '{"chat": {"history": []}}'

# Inspect recent traces with TraceQL-inspired filters
illumo trace list --traceql 'traces{} | pick(trace_id, root_service, start_time) | limit 10'
illumo trace search --traceql 'span.attributes["node_id"] == "inspect"'
illumo trace show --traceql 'trace_id == "TRACE_ID"' --format json --no-events

# Capture failure metadata
illumo run flow.yaml --context @ctx.json --report-path logs/failure.json --report-format markdown --log-dir logs
illumo trace search --timeout-only --format json
```

`illumo run` now emits a concise failure summary (trace ID, failing node, policy snapshot). Use `--report-path` / `--report-format` to persist the JSON/Markdown report and `--log-dir` to append entries under `runtime_execution.log`. Trace inspection commands accept `--format table|json|markdown`, while `trace show --format tree` renders a DAG view and `trace search --timeout-only` isolates timed-out spans.

Clone the repo if you want to explore samples locally:

```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow
illumo run examples/multi_agent/chat_bot/chatbot_flow.yaml --context '{"chat": {"history": []}}'
```

## YAML Configuration
Flows can also be defined in configuration files:

```yaml
flow:
  entry: extract
  nodes:
    extract:
      type: illumo_flow.core.FunctionNode
      name: extract
      context:
        inputs:
          callable: examples.ops.extract
        outputs: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        outputs: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        outputs: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

`context.inputs.callable` supplies the Python callable path for each node. Literal strings are imported at build time, while expressions (e.g. `$ctx.registry.my_func`) are evaluated during execution.

## Module Layout
- `illumo_flow.core` — Flow/Node orchestration primitives and DSL/YAML loaders
- `illumo_flow.policy` — Retry, timeout, and on-error models used by the runtime
- `illumo_flow.runtime` — Global runtime configuration, including `FlowRuntime` and `get_llm`
- `illumo_flow.tracing` — Console/SQLite/OTel tracer adapters implementing the Agents SDK contract
- `illumo_flow.llm` — Default LLM client helpers shared across Agent integrations

### Agent Nodes
- `illumo_flow.nodes.Agent` — renders prompts with context (`ctx.*`) and stores outputs under the configured `output_path` / `history_path` / `metadata_path` / `structured_path` (fallback: `ctx.agents.<node_id>`)
- `illumo_flow.nodes.RouterAgent` — chooses the next branch from a fixed `choices` list and records the decision plus rationale
- `illumo_flow.nodes.EvaluationAgent` — evaluates a target resource (`target` expression) and persists scores, reasons and structured JSON payloads

```python
from illumo_flow import FlowRuntime, Agent, RouterAgent, EvaluationAgent, NodeConfig

# Configure tracer/LLM defaults once
FlowRuntime.configure()

ctx = {"request": "All tests are green."}

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "Say hello to the reviewer."},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
        },
    )
)

router = RouterAgent(
    config=NodeConfig(
        name="Decision",
        setting={
            "prompt": {"type": "string", "value": "Context: {{ $ctx.request }}"},
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

review = EvaluationAgent(
    config=NodeConfig(
        name="Review",
        setting={
            "prompt": {"type": "string", "value": "Return JSON with fields 'score' and 'reasons'."},
            "target": {"type": "string", "value": "$ctx.messages.greeting"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

greeter.bind("greeter")
router.bind("decision")
review.bind("review")

greeter._execute({}, ctx)                 # writes greeting to ctx.messages.greeting
routing = router._execute({}, ctx)        # Routing(target='Ship'| 'Refine', reason='...')
score = review._execute({}, ctx)          # numeric score or structured JSON field
```

### Tracer Configuration
```python
from illumo_flow import FlowRuntime, ConsoleTracer, SQLiteTracer, OtelTracer

# Console tracer (default when FlowRuntime.configure is not called)
FlowRuntime.configure(tracer=ConsoleTracer())

# SQLite tracer persists spans and events to a database
FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))

# OTEL tracer forwards spans to a custom exporter
FlowRuntime.configure(
    tracer=OtelTracer(service_name="illumo-flow", exporter=my_exporter)
)
```

CLI equivalents:
```bash
illumo run flow.yaml --context '{"payload": {}}' --tracer sqlite --trace-db illumo_trace.db
illumo run flow.yaml --context '{"payload": {}}' --tracer otel --service-name demo-service
```

### Policy Configuration
`Policy` で fail-fast／retry／timeout／on_error を宣言的に指定できます。
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=True,
        timeout="15s",
        retry=Retry(max_attempts=2, delay="500ms", mode="exponential"),
        on_error=OnError(action="goto", target="fallback"),
    )
)
```
ノード側で `policy` を設定するとグローバルポリシーを上書きできます。

### Expressions
- `$ctx.*` accesses the shared context (e.g. `$ctx.data.raw`). Writing `ctx.*` or the shorthand `$.path` is automatically normalized to the same form.
- `$payload.*` reads from `context["payloads"]`
- `$joins.*` reads from `context["joins"]`
- `$env.VAR` reads environment variables
- Template strings like `"Hello {{ $ctx.user.name }}"` are supported in `inputs` definitions

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

### Payload vs Context
- Flow resolves each node's `payload` from the declared `inputs`.
- Nodes return the next `payload`; Flow stores it under `context["payloads"][node_id]` and writes to the paths declared in `outputs`.
- Treat the payload as the primary contract. When a callable needs shared state, use `self.request_context()` during execution and document the keys you mutate (e.g., `context.setdefault("metrics", {})`).

### Branching
- To route dynamically, return a dictionary mapping successor identifiers to payloads (e.g. `{"approve": payload}`). Only the listed successors are executed.
- Returning an empty dictionary `{}` stops downstream execution; returning multiple keys broadcasts to all corresponding successors.

## Testing (repository clone)
Keep runs short and deterministic by executing one test at a time.

- Update or extend scenarios inside `tests/test_flow_examples.py` (edit-only policy for this repo).
- Execute `pytest tests/test_flow_examples.py::TEST_NAME`; set `FLOW_DEBUG_MAX_STEPS=200` when exercising looping flows to guard against hangs.
- Track progress in `docs/test_checklist.md` and reset all checkboxes before regression sweeps.

Refer to `docs/test_checklist.md` for the live checklist.

## Documentation
- Architecture and API design: [docs/flow.md](docs/flow.md)
- Japanese version: [docs/flow_ja.md](docs/flow_ja.md)
- Concepts overview: [docs/concept.md](docs/concept.md)
- Quick tutorial reference: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)
- Chaptered tutorial (design foundations + samples): [docs/tutorials/README.md](docs/tutorials/README.md) / [docs/tutorials/README_ja.md](docs/tutorials/README_ja.md)

## Highlights
- DSL edges such as `A >> B`, `(A & B) >> C`
- Payload-first callable interface（共有コンテキストへアクセスする場合は `request_context()` で明示的に扱う）
- LoopNode for per-item iteration (self edge `loop >> loop` + body route `loop >> worker`)
- Branching via returned mappings (e.g. `{successor: payload}`)
- Built-in join handling (nodes with multiple parents automatically wait for all inputs)
- Examples covering ETL, dynamic routing, fan-out/fan-in, timeout handling, and early stop
