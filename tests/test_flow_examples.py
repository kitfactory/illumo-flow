from __future__ import annotations

import io
import json
import sqlite3
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

sys.modules.setdefault("tests.test_flow_examples", sys.modules[__name__])

from illumo_flow import (
    Flow,
    FlowError,
    FlowRuntime,
    Agent,
    RouterAgent,
    EvaluationAgent,
    FunctionNode,
    LoopNode,
    Policy,
    Routing,
    CustomRoutingNode,
    NodeConfig,
    ConsoleTracer,
    SQLiteTracer,
    OtelTracer,
    RuntimeExecutionReport,
)
from illumo_flow.core import get_llm
from examples import ops
from examples.sample_flows import EXAMPLE_FLOWS
from illumo_flow.cli import main as cli_main


RETRY_STATE: Dict[str, int] = {"count": 0}


def fn_policy_retry(payload: Any) -> str:
    RETRY_STATE["count"] += 1
    if RETRY_STATE["count"] < 2:
        raise RuntimeError("retry me")
    return "recovered"


def fn_policy_fail(_payload: Any) -> str:
    raise RuntimeError("boom")


def fn_policy_recover(payload: Any) -> str:
    return f"recovered:{payload}"


def fn_identity(payload: Any) -> Any:
    return payload


def fn_emit_label_a(payload: Any) -> Dict[str, str]:
    return {"label": "A"}


def fn_emit_label_b(payload: Any) -> Dict[str, str]:
    return {"label": "B"}


def fn_join_labels(payload: Mapping[str, Any]) -> str:
    return payload["A"]["label"] + payload["B"]["label"]


def fn_emit_mapping(payload: Any) -> Dict[str, int]:
    return {"a": 1, "b": 2}


def fn_collect(payload: Any, context: MutableMapping[str, Any]) -> Any:
    bucket = context.setdefault("results", [])
    bucket.append(payload)
    return payload


def fn_greet_city(payload: Mapping[str, Any]) -> str:
    return f"{payload['greeting']}:{payload['city']}"


def fn_bad_router(payload: Any) -> Routing:
    return Routing(target="next")


def make_function_node(
    *,
    name: str,
    callable_path: Optional[str] = None,
    callable_expression: Optional[str] = None,
    inputs: Optional[Any] = None,
    outputs: Optional[Any] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> FunctionNode:
    setting: Dict[str, Dict[str, Any]] = {}
    if callable_path is None and callable_expression is None:
        raise ValueError("callable_path or callable_expression must be provided")
    if callable_path is not None:
        setting["callable"] = {"type": "string", "value": callable_path}
    if callable_expression is not None:
        setting["callable_expression"] = {"type": "expression", "value": callable_expression}
    if metadata is not None:
        setting["metadata"] = {"type": "metadata", "value": metadata}
    return FunctionNode(
        config=NodeConfig(name=name, setting=setting, inputs=inputs, outputs=outputs)
    )


def make_routing_node(
    *,
    name: str,
    routing_rule_path: Optional[str] = None,
    routing_rule_expression: Optional[str] = None,
    inputs: Optional[Any] = None,
    outputs: Optional[Any] = None,
) -> CustomRoutingNode:
    setting: Dict[str, Dict[str, Any]] = {}
    if routing_rule_path is not None:
        setting["routing_rule"] = {"type": "string", "value": routing_rule_path}
    if routing_rule_expression is not None:
        setting["routing_rule_expression"] = {
            "type": "expression",
            "value": routing_rule_expression,
        }
    return CustomRoutingNode(
        config=NodeConfig(name=name, setting=setting, inputs=inputs, outputs=outputs)
    )


def make_loop_node(
    *,
    name: str,
    body_route: str,
    loop_route: Optional[str] = None,
    items_key: Optional[str] = None,
    enumerate_items: bool = False,
    inputs: Optional[Any] = None,
    outputs: Optional[Any] = None,
) -> LoopNode:
    setting: Dict[str, Dict[str, Any]] = {
        "body_route": {"type": "string", "value": body_route},
    }
    if loop_route is not None:
        setting["loop_route"] = {"type": "string", "value": loop_route}
    if items_key is not None:
        setting["items_key"] = {"type": "string", "value": items_key}
    if enumerate_items:
        setting["enumerate_items"] = {"type": "bool", "value": enumerate_items}
    return LoopNode(
        config=NodeConfig(name=name, setting=setting, inputs=inputs, outputs=outputs)
    )


def build_flow(example):
    return Flow.from_config({"flow": example["dsl"]})


@pytest.mark.parametrize("example", EXAMPLE_FLOWS, ids=lambda ex: ex["id"])
def test_examples_run_without_error(example):
    flow = build_flow(example)
    context = {}
    final_context = flow.run(context)
    assert context["steps"]  # execution trace is captured
    assert context["payloads"]  # node outputs are recorded
    assert example["dsl"]["entry"] in flow.nodes
    assert final_context is context
    if example["id"] == "linear_etl":
        assert context["data"]["persisted"] == "persisted"
    if example["id"] == "confidence_router":
        routing_entry = context["routing"].get("classify")
        assert routing_entry is not None
        assert isinstance(routing_entry, list)
        assert routing_entry
        first_route = routing_entry[0]
        assert "confidence" in first_route
        assert "target" in first_route
    if example["id"] == "early_stop_watchdog":
        guard_record = context["routing"].get("guard")
        assert guard_record is not None
        assert guard_record == []


def test_join_node_receives_parent_dictionary():
    module = __name__
    nodes = {
        "start": make_function_node(
            name="start", callable_path=f"{module}.fn_identity"
        ),
        "A": make_function_node(
            name="A", callable_path=f"{module}.fn_emit_label_a"
        ),
        "B": make_function_node(
            name="B", callable_path=f"{module}.fn_emit_label_b"
        ),
        "join": make_function_node(
            name="join", callable_path=f"{module}.fn_join_labels"
        ),
    }
    flow = Flow.from_dsl(
        nodes=nodes,
        entry="start",
        edges=["start >> (A | B)", "(A & B) >> join"],
    )
    ctx = {}
    final_context = flow.run(ctx, user_input="ignored")
    assert final_context is ctx
    assert ctx["payloads"]["join"] == "AB"
    assert ctx["joins"]["join"] == {
        "A": {"label": "A"},
        "B": {"label": "B"},
    }


def test_context_paths_are_honored():
    nodes = {
        "extract": make_function_node(
            name="extract",
            callable_path="examples.ops.extract",
            outputs="$ctx.data.raw",
        ),
        "transform": make_function_node(
            name="transform",
            callable_path="examples.ops.transform",
            inputs="$ctx.data.raw",
            outputs="$ctx.data.normalized",
        ),
        "load": make_function_node(
            name="load",
            callable_path="examples.ops.load",
            inputs="$ctx.data.normalized",
            outputs="$ctx.data.persisted",
        ),
    }

    flow = Flow.from_dsl(
        nodes=nodes,
        entry="extract",
        edges=["extract >> transform", "transform >> load"],
    )

    ctx = {}
    flow.run(ctx)
    assert ctx["data"]["raw"]["customer_id"] == 42
    assert ctx["data"]["normalized"]["normalized"] is True
    assert ctx["data"]["persisted"] == "persisted"


def test_multiple_outputs_configuration():
    nodes = {
        "producer": make_function_node(
            name="producer",
            callable_path=f"{__name__}.fn_emit_mapping",
            outputs={"a": "$ctx.data.alpha", "b": "$ctx.data.beta"},
        ),
    }

    flow = Flow.from_dsl(nodes=nodes, entry="producer", edges=[])
    ctx = {}
    flow.run(ctx)

    assert ctx["data"]["alpha"] == 1
    assert ctx["data"]["beta"] == 2


def test_flow_from_yaml_config(tmp_path):
    config_text = textwrap.dedent(
        """
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
        """
    )

    config_path = tmp_path / "flow.yaml"
    config_path.write_text(config_text)

    flow = Flow.from_config(config_path)
    ctx = {}
    flow.run(ctx)

    assert ctx["data"]["persisted"] == "persisted"
    assert ctx["payloads"]["load"] == "persisted"

    # Also allow passing dictionaries directly
    config_dict = yaml.safe_load(config_text)
    flow_from_dict = Flow.from_config(config_dict)
    ctx2 = {}
    flow_from_dict.run(ctx2)
    assert ctx2["data"]["persisted"] == "persisted"


def test_expression_inputs_and_env(monkeypatch):
    monkeypatch.setenv("CITY", "Tokyo")

    nodes = {
        "greet": make_function_node(
            name="greet",
            callable_path=f"{__name__}.fn_greet_city",
            inputs={
                "greeting": "おはようございます {{ $.user.name }}",
                "city": "$env.CITY",
            },
            outputs="$.data.message",
        ),
    }

    flow = Flow.from_dsl(nodes=nodes, entry="greet", edges=[])
    ctx = {"user": {"name": "太郎", "email": "taro@example.com"}}
    flow.run(ctx)
    assert ctx["data"]["message"] == "おはようございます 太郎:Tokyo"


def test_callable_resolved_from_context_expression():
    nodes = {
        "dyn": make_function_node(
            name="dyn",
            callable_expression="$.registry.greeter",
            outputs="$ctx.data.value",
        )
    }

    flow = Flow.from_dsl(nodes=nodes, entry="dyn", edges=[])
    ctx = {"registry": {"greeter": ops.extract}}
    flow.run(ctx)

    assert ctx["data"]["value"]["customer_id"] == 42
    assert ctx["data"]["value"]["source"] == "demo"


def test_function_node_returning_routing_is_rejected():
    module = __name__
    nodes = {
        "start": make_function_node(
            name="start", callable_path=f"{module}.fn_bad_router"
        ),
        "next": make_function_node(
            name="next", callable_path=f"{module}.fn_identity"
        ),
    }

    flow = Flow.from_dsl(nodes=nodes, entry="start", edges=["start >> next"])
    with pytest.raises(FlowError):
        flow.run({})


def test_loop_node_iterates_over_sequence():
    def collect(payload, context):
        bucket = context.setdefault("results", [])
        bucket.append(payload)
        return payload

    nodes = {
        "loop": make_loop_node(
            name="loop",
            body_route="worker",
            enumerate_items=True,
        ),
        "worker": make_function_node(
            name="worker",
            callable_path=f"{__name__}.fn_collect",
        ),
    }

    flow = Flow.from_dsl(
        nodes=nodes,
        entry="loop",
        edges=["loop >> worker", "loop >> loop"],
    )

    ctx = {}
    flow.run(ctx, user_input=["a", "b", "c"])

    assert ctx["results"] == [
        {"item": "a", "index": 0},
        {"item": "b", "index": 1},
        {"item": "c", "index": 2},
    ]
    assert ctx["payloads"]["worker"] == {"item": "c", "index": 2}


def test_policy_retry_recovers(monkeypatch):
    RETRY_STATE["count"] = 0

    retry_node = FunctionNode(
        config=NodeConfig(
            name="RetryNode",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_policy_retry"},
                "policy": {
                    "type": "mapping",
                    "value": {"retry": {"max_attempts": 2, "delay": 0}},
                },
            },
        )
    )
    flow = Flow.from_dsl(nodes={"Retry": retry_node}, entry="Retry", edges=[])

    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=previous_runtime.tracer,
        policy=Policy(),
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        ctx: Dict[str, Any] = {}
        flow.run(ctx)
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )

    assert ctx["payloads"]["Retry"] == "recovered"
    assert RETRY_STATE["count"] == 2


def test_policy_on_error_continue_moves_forward():
    fail_node = FunctionNode(
        config=NodeConfig(
            name="Fail",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_policy_fail"},
                "policy": {
                    "type": "mapping",
                    "value": {"on_error": {"action": "continue"}},
                },
            },
        )
    )
    success_node = FunctionNode(
        config=NodeConfig(
            name="Success",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_identity"},
                "outputs": {"type": "string", "value": "data.ok"},
            },
        )
    )
    flow = Flow.from_dsl(
        nodes={"Fail": fail_node, "Success": success_node},
        entry="Fail",
        edges=["Fail >> Success"],
    )

    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=previous_runtime.tracer,
        policy=Policy(fail_fast=False),
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        ctx: Dict[str, Any] = {"data": {"ok": "initial"}}
        flow.run(ctx)
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )

    assert ctx["data"]["ok"] == "initial"
    fail_steps = [step for step in ctx["steps"] if step["node_id"] == "Fail"]
    assert any(step.get("status") == "failed" for step in fail_steps)
    assert any(step.get("status") == "continue" for step in fail_steps)


def test_runtime_execution_report_captures_failure():
    fail_node = FunctionNode(
        config=NodeConfig(
            name="Fail",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_policy_fail"},
            },
        )
    )
    flow = Flow.from_dsl(nodes={"Fail": fail_node}, entry="Fail", edges=[])

    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=ConsoleTracer(stream=io.StringIO()),
        policy=Policy(),
        llm_factory=previous_runtime.llm_factory,
    )

    report = RuntimeExecutionReport()
    try:
        with pytest.raises(RuntimeError):
            flow.run({}, report=report)
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )

    assert report.trace_id
    assert report.failed_node_id == "Fail"
    assert report.summary == "boom"
    assert report.policy_snapshot.get("fail_fast") is True
    assert "payload_preview" in report.context_digest


def test_policy_on_error_goto_routes_to_target():
    fail_node = FunctionNode(
        config=NodeConfig(
            name="Primary",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_policy_fail"},
                "policy": {
                    "type": "mapping",
                    "value": {"on_error": {"action": "goto", "target": "Recover"}},
                },
            },
        )
    )
    recover_node = FunctionNode(
        config=NodeConfig(
            name="Recover",
            setting={
                "callable": {"type": "string", "value": "tests.test_flow_examples.fn_policy_recover"},
                "outputs": {"type": "string", "value": "data.recover"},
            },
        )
    )
    flow = Flow.from_dsl(
        nodes={"Primary": fail_node, "Recover": recover_node},
        entry="Primary",
        edges=["Primary >> Recover"],
    )

    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=previous_runtime.tracer,
        policy=Policy(),
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        ctx: Dict[str, Any] = {}
        flow.run(ctx)
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )

    assert ctx["payloads"]["Recover"] == "recovered:None"
    goto_steps = [step for step in ctx["steps"] if step["node_id"] == "Primary"]
    assert any(step.get("status") == "goto" for step in goto_steps)


def test_get_llm_appends_v1_suffix_when_missing():
    client = get_llm("lmstudio", "dummy-model", base_url="http://localhost:1234")
    base_url = getattr(client, "base_url", None)
    if base_url is not None:
        base_url = str(base_url).rstrip("/")
    assert base_url == "http://localhost:1234/v1"


def test_get_llm_keeps_existing_v1_suffix():
    client = get_llm("openai", "dummy-model", base_url="http://localhost:1234/v1")
    base_url = getattr(client, "base_url", None)
    if base_url is not None:
        base_url = str(base_url).rstrip("/")
    assert base_url == "http://localhost:1234/v1"


def test_get_llm_defaults_to_openai_when_unspecified():
    client = get_llm(None, "gpt-4.1-mini")
    assert getattr(client, "_illumo_provider", None) == "openai"


def test_get_llm_respects_explicit_provider_priority():
    client = get_llm("lmstudio", "openai/gpt-oss-20b", base_url="http://192.168.11.16:1234")
    assert getattr(client, "_illumo_provider", None) == "lmstudio"


def test_agent_openai_writes_to_configured_paths():
    config = NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "Say hello to {{ $ctx.user.name }}"},
            "output_path": {"type": "string", "value": "$ctx.data.openai_reply"},
        },
    )
    agent = Agent(config=config)
    agent.bind("openai_agent")

    ctx: Dict[str, Any] = {"user": {"name": "Alice"}}
    response = agent._execute({}, ctx)

    assert isinstance(response, str) and response.strip()
    assert ctx["data"]["openai_reply"].strip() == response.strip()
    agents_bucket = ctx["agents"]["openai_agent"]
    assert "response" not in agents_bucket


def test_agent_lmstudio_writes_to_agents_bucket():
    config = NodeConfig(
        name="LMStudioAgent",
        setting={
            "provider": {"type": "string", "value": "lmstudio"},
            "model": {"type": "string", "value": "openai/gpt-oss-20b"},
            "base_url": {"type": "string", "value": "http://192.168.11.16:1234"},
            "prompt": {"type": "string", "value": "Summarize {{ $ctx.topic }} in one sentence."},
        },
    )
    agent = Agent(config=config)
    agent.bind("lmstudio_agent")

    ctx: Dict[str, Any] = {"topic": "product update"}
    response = agent._execute({}, ctx)

    assert isinstance(response, str) and response.strip()
    agents_bucket = ctx["agents"]["lmstudio_agent"]
    assert agents_bucket["response"]["value"].strip() == response.strip()


def test_router_agent_selects_route_with_reason():
    config = NodeConfig(
        name="Router",
        setting={
            "prompt": {
                "type": "string",
                "value": "Context: {{ $ctx.request }}",
            },
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
    agent = RouterAgent(config=config)
    agent.bind("router_agent")

    ctx: Dict[str, Any] = {"request": "All tests are green and documentation is updated."}
    routing = agent._execute({}, ctx)

    assert isinstance(routing, Routing)
    assert routing.target in {"Ship", "Refine"}
    assert ctx["route"]["decision"] in {"Ship", "Refine"}
    assert ctx["routing"]["router_agent"]


def test_evaluation_agent_records_score_and_metadata():
    config = NodeConfig(
        name="Reviewer",
        setting={
            "prompt": {
                "type": "string",
                "value": "Provide JSON with fields 'score' and 'reasons'.",
            },
            "target": {"type": "string", "value": "$ctx.proposal"},
            "output_path": {"type": "string", "value": "$ctx.metrics.review_score"},
            "metadata_path": {"type": "string", "value": "$ctx.metrics.review_reason"},
            "structured_path": {
                "type": "string", "value": "$ctx.metrics.review_details"
            },
        },
    )
    agent = EvaluationAgent(config=config)
    agent.bind("review_agent")

    ctx: Dict[str, Any] = {"proposal": "Introduce better onboarding messaging."}
    score = agent._execute({}, ctx)

    assert score is not None
    metrics_bucket = ctx["metrics"]["review_agent"]
    assert metrics_bucket and "score" in metrics_bucket[0]
    assert "review_score" in ctx["metrics"]


def test_console_tracer_emits_flow_and_node_spans():
    stream = io.StringIO()
    tracer = ConsoleTracer(stream=stream, enable_color=False)
    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=tracer,
        policy=previous_runtime.policy,
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        module = __name__
        nodes = {
            "start": make_function_node(
                name="start",
                callable_path=f"{module}.fn_identity",
            ),
        }
        flow = Flow.from_dsl(nodes=nodes, entry="start", edges=[])
        ctx: Dict[str, Any] = {}
        flow.run(ctx, user_input="hello")
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )
    output = stream.getvalue()
    assert "[FLOW]" in output
    assert "[NODE]" in output


def test_sqlite_tracer_persists_spans(tmp_path):
    db_path = tmp_path / "trace.db"
    tracer = SQLiteTracer(db_path=str(db_path))
    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=tracer,
        policy=previous_runtime.policy,
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        module = __name__
        nodes = {
            "start": make_function_node(
                name="start",
                callable_path=f"{module}.fn_identity",
            ),
            "second": make_function_node(
                name="second",
                callable_path=f"{module}.fn_identity",
            ),
        }
        flow = Flow.from_dsl(nodes=nodes, entry="start", edges=["start >> second"])
        ctx: Dict[str, Any] = {}
        flow.run(ctx, user_input="hello")
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )
        tracer.close()

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM spans WHERE kind = ?", ("node",))
        node_spans = cur.fetchone()[0]
        assert node_spans >= 1


def test_otel_tracer_exports_spans():
    exported: list[Mapping[str, Any]] = []

    class DummyExporter:
        def export(self, spans: Sequence[Mapping[str, Any]]) -> None:
            exported.extend(spans)

    tracer = OtelTracer(service_name="illumo-flow", exporter=DummyExporter())
    previous_runtime = FlowRuntime.current()
    FlowRuntime.configure(
        tracer=tracer,
        policy=previous_runtime.policy,
        llm_factory=previous_runtime.llm_factory,
    )
    try:
        module = __name__
        nodes = {
            "start": make_function_node(
                name="start",
                callable_path=f"{module}.fn_identity",
            ),
        }
        flow = Flow.from_dsl(nodes=nodes, entry="start", edges=[])
        ctx: Dict[str, Any] = {}
        flow.run(ctx, user_input="hello")
    finally:
        FlowRuntime.configure(
            tracer=previous_runtime.tracer,
            policy=previous_runtime.policy,
            llm_factory=previous_runtime.llm_factory,
        )

    assert any(span.get("kind") == "flow" for span in exported)
    assert any(span.get("kind") == "node" for span in exported)


def test_cli_run_happy_path(tmp_path: Path) -> None:
    flow_path = tmp_path / "flow.yaml"
    flow_path.write_text(
        textwrap.dedent(
            """
            flow:
              entry: start
              nodes:
                start:
                  type: illumo_flow.core.FunctionNode
                  context:
                    inputs:
                      callable: tests.test_flow_examples.fn_emit_mapping
                    outputs: $ctx.result
              edges: []
            """
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "ctx.json"

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli_main(
        [
            "run",
            str(flow_path),
            "--context",
            "{}",
            "--output",
            str(output_path),
            "--pretty",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert not stderr.getvalue()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["result"] == {"a": 1, "b": 2}
    assert payload["payloads"]["start"] == {"a": 1, "b": 2}


def test_cli_run_reports_failure(tmp_path: Path) -> None:
    flow_path = tmp_path / "fail_flow.yaml"
    flow_path.write_text(
        textwrap.dedent(
            """
            flow:
              entry: boom
              nodes:
                boom:
                  type: illumo_flow.core.FunctionNode
                  context:
                    inputs:
                      callable: tests.test_flow_examples.fn_policy_fail
              edges: []
            """
        ),
        encoding="utf-8",
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli_main(
        [
            "run",
            str(flow_path),
            "--context",
            "{}",
            "--log-dir",
            str(tmp_path / "logs"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    message = stderr.getvalue()
    assert "Flow failed." in message
    assert "trace_id:" in message
    assert "failed_node: boom" in message
    assert "reason: boom" in message

    log_path = tmp_path / "logs" / "runtime_execution.log"
    assert log_path.exists()
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert entries
    assert entries[-1]["failed_node_id"] == "boom"
