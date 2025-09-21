from __future__ import annotations

import pytest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from illumo_flow import Flow, FunctionNode
from examples import ops
from examples.sample_flows import EXAMPLE_FLOWS


def build_flow(example):
    nodes = {}
    for node_id, node_cfg in example["dsl"]["nodes"].items():
        callable_path = node_cfg["callable"].split(".")[-1]
        func = getattr(ops, callable_path)
        context_cfg = node_cfg.get("context", {})
        node = FunctionNode(
            func,
            input_path=context_cfg.get("input"),
            output_path=context_cfg.get("output"),
        )
        if "default_route" in node_cfg:
            node.default_route = node_cfg["default_route"]
        nodes[node_id] = node
    edges = example["dsl"].get("edges", [])
    return Flow.from_dsl(nodes=nodes, entry=example["dsl"]["entry"], edges=edges)


@pytest.mark.parametrize("example", EXAMPLE_FLOWS, ids=lambda ex: ex["id"])
def test_examples_run_without_error(example):
    flow = build_flow(example)
    context = {}
    result = flow.run(context)
    assert context["steps"]  # execution trace is captured
    assert context["payloads"]  # node outputs are recorded
    assert example["dsl"]["entry"] in flow.nodes
    assert result in context["payloads"].values()
    if example["id"] == "linear_etl":
        assert context["data"]["persisted"] == "persisted"


def test_join_node_receives_parent_dictionary():
    def make_value(label):
        return lambda ctx, payload: {"label": label}

    nodes = {
        "start": FunctionNode(lambda ctx, payload: payload),
        "A": FunctionNode(make_value("A")),
        "B": FunctionNode(make_value("B")),
        "join": FunctionNode(lambda ctx, payload: payload["A"]["label"] + payload["B"]["label"]),
    }
    flow = Flow.from_dsl(
        nodes=nodes,
        entry="start",
        edges=["start >> (A | B)", "(A & B) >> join"],
    )
    ctx = {}
    result = flow.run(ctx, user_input="ignored")
    assert result == "AB"
    assert ctx["joins"]["join"] == {
        "A": {"label": "A"},
        "B": {"label": "B"},
    }


def test_context_paths_are_honored():
    nodes = {
        "extract": FunctionNode(
            ops.extract,
            output_path="data.raw",
        ),
        "transform": FunctionNode(
            ops.transform,
            input_path="data.raw",
            output_path="data.normalized",
        ),
        "load": FunctionNode(
            ops.load,
            input_path="data.normalized",
            output_path="data.persisted",
        ),
    }

    flow = Flow.from_dsl(
        nodes=nodes,
        entry="extract",
        edges=["extract >> transform", "transform >> load"],
    )

    ctx = {}
    result = flow.run(ctx)

    assert result == "persisted"
    assert ctx["data"]["raw"]["customer_id"] == 42
    assert ctx["data"]["normalized"]["normalized"] is True
    assert ctx["data"]["persisted"] == "persisted"
