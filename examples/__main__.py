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

from illumo_flow import Flow
from .sample_flows import EXAMPLE_FLOWS


def build_flow(example_id: str) -> Flow:
    example = next((ex for ex in EXAMPLE_FLOWS if ex["id"] == example_id), None)
    if example is None:
        raise SystemExit(f"Example '{example_id}' not found")
    return Flow.from_config({"flow": example["dsl"]})


def main(argv: Any = None) -> None:
    parser = argparse.ArgumentParser(description="Run illumo_flow sample flows")
    parser.add_argument("example_id", choices=[ex["id"] for ex in EXAMPLE_FLOWS], help="Example flow identifier")
    args = parser.parse_args(argv)
    flow = build_flow(args.example_id)
    context = {}
    flow.run(context)
    print("payloads:", context["payloads"])
    print("steps:", context["steps"])


if __name__ == "__main__":
    main()
