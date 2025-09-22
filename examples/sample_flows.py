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
            "Context accumulation via $ctx.data.raw and $ctx.data.normalized",
            "Fail-fast propagation when middle node raises",
        ],
        "dsl": {
            "entry": "extract",
            "nodes": {
                "extract": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Read source payload",
                        "context_outputs": ["$ctx.data.raw"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.extract",
                        },
                        "outputs": "$ctx.data.raw",
                    },
                },
                "transform": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Normalize raw payload",
                        "context_inputs": ["$ctx.data.raw"],
                        "context_outputs": ["$ctx.data.normalized"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.transform",
                            "payload": "$ctx.data.raw",
                        },
                        "outputs": "$ctx.data.normalized",
                    },
                },
                "load": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Persist normalized payload",
                        "context_inputs": ["$ctx.data.normalized"],
                        "context_outputs": ["$ctx.data.persisted"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.load",
                            "payload": "$ctx.data.normalized",
                        },
                        "outputs": "$ctx.data.persisted",
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
            "Audit trail stored under `$ctx.routing.classify`",
            "Fallback target via `default_route` when confidence is low",
        ],
        "dsl": {
            "entry": "classify",
            "nodes": {
                "classify": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Choose approve/reject path",
                        "context_outputs": ["$ctx.routing.classify"],
                    },
                    "default_route": "manual_review",
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.classify",
                        },
                    },
                },
                "approve": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Auto approval",
                        "context_inputs": ["$ctx.inputs.application"],
                        "context_outputs": ["$ctx.decisions.auto"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.approve",
                        },
                        "outputs": "$ctx.decisions.auto",
                    },
                },
                "reject": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Auto rejection",
                        "context_inputs": ["$ctx.inputs.application"],
                        "context_outputs": ["$ctx.decisions.auto"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.reject",
                        },
                        "outputs": "$ctx.decisions.auto",
                    },
                },
                "manual_review": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Escalate to human reviewer",
                        "context_outputs": ["$ctx.decisions.manual_review"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.manual_review",
                        },
                        "outputs": "$ctx.decisions.manual_review",
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
            "Join buffer consolidation under `$joins.merge`",
            "Downstream node consumes deterministic merged payload",
        ],
        "dsl": {
            "entry": "seed",
            "nodes": {
                "seed": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Seed enrichment inputs",
                        "context_outputs": ["$ctx.data.customer"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.seed",
                        },
                        "outputs": "$ctx.data.customer",
                    },
                },
                "geo": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Geo enrichment",
                        "context_inputs": ["$ctx.data.customer"],
                        "context_outputs": ["$ctx.data.geo"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.enrich_geo",
                            "payload": "$ctx.data.customer",
                        },
                        "outputs": "$ctx.data.geo",
                    },
                },
                "risk": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Risk enrichment",
                        "context_inputs": ["$ctx.data.customer"],
                        "context_outputs": ["$ctx.data.risk"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.enrich_risk",
                            "payload": "$ctx.data.customer",
                        },
                        "outputs": "$ctx.data.risk",
                    },
                },
                "merge": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Merge geo and risk",
                        "context_inputs": ["$joins.merge.geo", "$joins.merge.risk"],
                        "context_outputs": ["$ctx.data.profile"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.merge_enrichment",
                        },
                        "outputs": "$ctx.data.profile",
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
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Invoke external API with internal timeout",
                        "context_outputs": ["$ctx.data.api_response"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.call_api_with_timeout",
                        },
                        "outputs": "$ctx.data.api_response",
                    },
                },
                "parse": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Parse API response",
                        "context_inputs": ["$ctx.data.api_response"],
                        "context_outputs": ["$ctx.data.api_parsed"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.parse_response",
                            "payload": "$ctx.data.api_response",
                        },
                        "outputs": "$ctx.data.api_parsed",
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
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Check thresholds before proceeding",
                        "context_outputs": ["$ctx.routing.guard"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.guard_threshold",
                        },
                    },
                },
                "continue": {
                    "type": "illumo_flow.core.FunctionNode",
                    "describe": {
                        "summary": "Downstream work reached only if guard allows",
                        "context_outputs": ["$ctx.data.final"],
                    },
                    "context": {
                        "inputs": {
                            "callable": "examples.ops.continue_flow",
                        },
                        "outputs": "$ctx.data.final",
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
