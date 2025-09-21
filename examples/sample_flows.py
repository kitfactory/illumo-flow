"""Reference flow definitions used to exercise core illumo Flow scenarios."""

from __future__ import annotations

from typing import Any, Dict, List

SampleFlow = Dict[str, Any]

EXAMPLE_FLOWS: List[SampleFlow] = [
    {
        "id": "linear_etl",
        "description": "Sequential ETL pipeline that must respect ordering and fail fast.",
        "important_points": [
            "Deterministic node order",
            "Context accumulation (`context.outputs.raw`, `context.outputs.transformed`)",
            "Fail-fast propagation when middle node raises",
        ],
        "dsl": {
            "entry": "extract",
            "nodes": {
                "extract": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.extract",
                    "describe": {
                        "summary": "Read source payload",
                        "context_outputs": ["outputs.raw"],
                    },
                    "context": {
                        "outputs": "data.raw",
                    },
                },
                "transform": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.transform",
                    "describe": {
                        "summary": "Normalize raw payload",
                        "context_inputs": ["outputs.raw"],
                        "context_outputs": ["outputs.normalized"],
                    },
                    "context": {
                        "inputs": "data.raw",
                        "outputs": "data.normalized",
                    },
                },
                "load": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.load",
                    "describe": {
                        "summary": "Persist normalized payload",
                        "context_inputs": ["outputs.normalized"],
                        "context_outputs": ["outputs.persisted"],
                    },
                    "context": {
                        "inputs": "data.normalized",
                        "outputs": "data.persisted",
                    },
                },
            },
            "edges": [
                "extract >> transform",
                "transform >> load",
            ],
        },
    },
    {
        "id": "confidence_router",
        "description": "Router node selects downstream path using confidence scores.",
        "important_points": [
            "Node-managed routing metadata with `Routing.next` and `Routing.confidence`",
            "Audit trail stored under `context.routing.classify`",
            "Fallback target via `default_route` when confidence is low",
        ],
        "dsl": {
            "entry": "classify",
            "nodes": {
                "classify": {
                    "type": "illumo.nodes.RouterNode",
                    "callable": "examples.ops.classify",
                    "describe": {
                        "summary": "Choose approve/reject path",
                        "context_outputs": ["routing.classify"],
                    },
                    "default_route": "manual_review",
                },
                "approve": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.approve",
                    "describe": {
                        "summary": "Auto approval",
                        "context_inputs": ["inputs.application"],
                        "context_outputs": ["outputs.decision"],
                    },
                    "context": {
                        "outputs": "decisions.auto",
                    },
                },
                "reject": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.reject",
                    "describe": {
                        "summary": "Auto rejection",
                        "context_inputs": ["inputs.application"],
                        "context_outputs": ["outputs.decision"],
                    },
                    "context": {
                        "outputs": "decisions.auto",
                    },
                },
                "manual_review": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.manual_review",
                    "describe": {
                        "summary": "Escalate to human reviewer",
                        "context_outputs": ["outputs.review_ticket"],
                    },
                    "context": {
                        "outputs": "decisions.manual_review",
                    },
                },
            },
            "edges": [
                "classify >> (approve | reject | manual_review)",
            ],
        },
    },
    {
        "id": "parallel_enrichment",
        "description": "Fan-out to enrichment nodes and fan-in via join requirements.",
        "important_points": [
            "Parallel scheduling across geo/risk",
            "Join buffer consolidation under `context.joins.enrich`",
            "Downstream node consumes deterministic merged payload",
        ],
        "dsl": {
            "entry": "seed",
            "nodes": {
                "seed": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.seed",
                    "describe": {
                        "summary": "Seed enrichment inputs",
                        "context_outputs": ["inputs.customer"],
                    },
                    "context": {
                        "outputs": "data.customer",
                    },
                },
                "geo": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.enrich_geo",
                    "describe": {
                        "summary": "Geo enrichment",
                        "context_inputs": ["inputs.customer"],
                        "context_outputs": ["joins.enrich.geo"],
                    },
                    "context": {
                        "inputs": "data.customer",
                        "outputs": "data.geo",
                    },
                },
                "risk": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.enrich_risk",
                    "describe": {
                        "summary": "Risk enrichment",
                        "context_inputs": ["inputs.customer"],
                        "context_outputs": ["joins.enrich.risk"],
                    },
                    "context": {
                        "inputs": "data.customer",
                        "outputs": "data.risk",
                    },
                },
                "merge": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.merge_enrichment",
                    "describe": {
                        "summary": "Merge geo and risk",
                        "context_inputs": ["joins.enrich.geo", "joins.enrich.risk"],
                        "context_outputs": ["outputs.profile"],
                    },
                    "context": {
                        "outputs": "data.profile",
                    },
                },
            },
            "edges": [
                "seed >> (geo | risk)",
                "(geo & risk) >> merge",
            ],
        },
    },
    {
        "id": "node_managed_timeout",
        "description": "Node encapsulates its own timeout/retry discipline before surfacing errors.",
        "important_points": [
            "Retries and timeouts happen inside the node implementation",
            "Flow remains fail-fast once exceptions escape",
            "Context logs include attempt metadata under `context.steps`",
        ],
        "dsl": {
            "entry": "call_api",
            "nodes": {
                "call_api": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.call_api_with_timeout",
                    "describe": {
                        "summary": "Invoke external API with internal timeout",
                        "context_outputs": ["outputs.api_response"],
                    },
                    "context": {
                        "outputs": "data.api_response",
                    },
                },
                "parse": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.parse_response",
                    "describe": {
                        "summary": "Parse API response",
                        "context_inputs": ["outputs.api_response"],
                        "context_outputs": ["outputs.parsed"],
                    },
                    "context": {
                        "inputs": "data.api_response",
                        "outputs": "data.api_parsed",
                    },
                },
            },
            "edges": [
                "call_api >> parse",
            ],
        },
    },
    {
        "id": "early_stop_watchdog",
        "description": "Flow terminates gracefully when guard requests stop routing.",
        "important_points": [
            "Guard node writes `Routing.next = None` with a reason",
            "Execution trace captures termination cause",
            "No downstream tasks remain pending after stop",
        ],
        "dsl": {
            "entry": "guard",
            "nodes": {
                "guard": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.guard_threshold",
                    "describe": {
                        "summary": "Check thresholds before proceeding",
                        "context_outputs": ["routing.guard"],
                    },
                },
                "continue": {
                    "type": "illumo.nodes.FunctionNode",
                    "callable": "examples.ops.continue_flow",
                    "describe": {
                        "summary": "Downstream work reached only if guard allows",
                        "context_outputs": ["outputs.final"],
                    },
                },
            },
            "edges": [
                "guard >> continue",
            ],
        },
    },
]


def list_examples() -> List[SampleFlow]:
    return EXAMPLE_FLOWS


if __name__ == "__main__":
    import json

    print(json.dumps(EXAMPLE_FLOWS, indent=2, ensure_ascii=False))
