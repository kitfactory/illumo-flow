# illumo-flow

Workflow orchestration primitives featuring declarative DSL wiring, routing control, and fail-fast execution.

## Why developers pick illumo-flow
1. **Model hopping stays painless**: the runtime smooths out provider quirks (OpenAI, Anthropic, LM Studio, Ollama, …), so the same code runs from experiment to production without worrying about `/v1` suffixes or bespoke parameters.
2. **Agent flows stay explicit**: define the flow in a tiny DSL, wire it through the orchestrator, and keep conversational steps, routers, and evaluators under tight control instead of scattering logic across scripts.
3. **Tracing becomes fun**: flip a single setting to move from colorized console transcripts to durable SQLite trails (and OTEL exporters next), finally retiring the print-debug routine.
4. **Policies do the heavy lifting**: relax during development with lenient retries, then tighten fail-fast rules in production purely through configuration—no code edits required.
5. **CLI, YAML, and Python align**: prototypes, shared specs, and embedded code all read the same, making handoff between teammates effortless.
6. **Context doubles as a mission log**: every run leaves behind a narrative the whole team can review quickly and audit when needed.

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
The GitHub repository ships reference examples and a CLI (e.g. `python -m examples linear_etl`).
Clone the repo if you want to explore them locally:
```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow
python -m examples linear_etl
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

CLI からも切り替え可能です。
```bash
illumo run flow.yaml --tracer sqlite --tracer-arg db_path=./trace.db
illumo run flow.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317
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
