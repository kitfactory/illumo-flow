from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from illumo_flow import Flow, FlowError, FunctionNode, LoopNode, Routing, CustomRoutingNode
from examples import ops
from examples.sample_flows import EXAMPLE_FLOWS


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
    def make_value(label):
        return lambda payload: {"label": label}

    nodes = {
        "start": FunctionNode(lambda payload: payload, name="start"),
        "A": FunctionNode(make_value("A"), name="A"),
        "B": FunctionNode(make_value("B"), name="B"),
        "join": FunctionNode(
            lambda payload: payload["A"]["label"] + payload["B"]["label"],
            name="join",
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
        "extract": FunctionNode(ops.extract, name="extract", outputs="$ctx.data.raw"),
        "transform": FunctionNode(
            ops.transform,
            name="transform",
            inputs="$ctx.data.raw",
            outputs="$ctx.data.normalized",
        ),
        "load": FunctionNode(
            ops.load,
            name="load",
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
    def producer(payload):
        return {"a": 1, "b": 2}

    nodes = {
        "producer": FunctionNode(
            producer,
            name="producer",
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
        "greet": FunctionNode(
            lambda payload: f"{payload['greeting']}:{payload['city']}",
            name="greet",
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
        "dyn": FunctionNode(
            callable_expression="$.registry.greeter",
            name="dyn",
            outputs="$ctx.data.value",
        )
    }

    flow = Flow.from_dsl(nodes=nodes, entry="dyn", edges=[])
    ctx = {"registry": {"greeter": ops.extract}}
    flow.run(ctx)

    assert ctx["data"]["value"]["customer_id"] == 42
    assert ctx["data"]["value"]["source"] == "demo"


def test_function_node_returning_routing_is_rejected():
    def bad_router(payload):
        return Routing(target="next")

    nodes = {
        "start": FunctionNode(bad_router, name="start"),
        "next": FunctionNode(lambda payload: payload, name="next"),
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
        "loop": LoopNode(name="loop", body_route="worker", enumerate_items=True),
        "worker": FunctionNode(
            collect,
            name="worker",
            allow_context_access=True,
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
