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
        node = FunctionNode(func)
        for parent in node_cfg.get("requires", []):
            node.requires(parent)
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
