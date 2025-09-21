"""Run sample flows directly from the examples package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from illumo_flow import Flow, FunctionNode

from . import ops
from .sample_flows import EXAMPLE_FLOWS


def build_flow(example_id: str) -> Flow:
    example = next((ex for ex in EXAMPLE_FLOWS if ex["id"] == example_id), None)
    if example is None:
        raise SystemExit(f"Example '{example_id}' not found")
    nodes = {}
    for node_id, node_cfg in example["dsl"]["nodes"].items():
        func_name = node_cfg["callable"].split(".")[-1]
        func = getattr(ops, func_name)
        node = FunctionNode(func)
        for parent in node_cfg.get("requires", []):
            node.requires(parent)
        if "default_route" in node_cfg:
            node.default_route = node_cfg["default_route"]
        nodes[node_id] = node
    flow = Flow.from_dsl(nodes=nodes, entry=example["dsl"]["entry"], edges=example["dsl"].get("edges", []))
    return flow


def main(argv: Any = None) -> None:
    parser = argparse.ArgumentParser(description="Run illumo_flow sample flows")
    parser.add_argument("example_id", choices=[ex["id"] for ex in EXAMPLE_FLOWS], help="Example flow identifier")
    args = parser.parse_args(argv)
    flow = build_flow(args.example_id)
    context = {}
    result = flow.run(context)
    print("result:", result)
    print("steps:", context["steps"])
    print("payloads:", context["payloads"])


if __name__ == "__main__":
    main()
