"""Example node callables for illumo_flow demonstrations."""

from __future__ import annotations

from random import random
from typing import Any, Dict, List, Tuple

from illumo_flow.core import Routing


def extract(payload: Any) -> Dict[str, Any]:
    return {"customer_id": 42, "source": "demo"}


def transform(payload: Any) -> Dict[str, Any]:
    raw = payload or {}
    return {**raw, "normalized": True}


def load(payload: Any) -> str:
    return "persisted"


def classify(payload: Any, ctx) -> Routing:
    confidence_score = int(random() * 100)
    metrics = ctx.setdefault("metrics", {})
    metrics["score"] = confidence_score

    if confidence_score > 70:
        target = "approve"
        reason = "confidence above auto-approval threshold"
    elif confidence_score < 30:
        target = "manual_review"
        reason = "confidence below manual review threshold"
    else:
        target = "reject"
        reason = "confidence within automatic reject band"

    normalized_confidence = confidence_score / 100.0
    return Routing(
        target=target,
        confidence=normalized_confidence,
        reason=reason,
    ), payload


def approve(payload: Any) -> str:
    return "approved"


def reject(payload: Any) -> str:
    return "rejected"


def manual_review(payload: Any) -> Dict[str, Any]:
    return {"id": "TICKET-1", "status": "queued"}


def seed(payload: Any) -> Dict[str, Any]:
    return {"id": 1, "segment": "SMB"}


def enrich_geo(payload: Any) -> Dict[str, Any]:
    return {"country": "JP", "region": "Kanto"}


def enrich_risk(payload: Any) -> Dict[str, Any]:
    return {"score": 0.2, "band": "low"}


def merge_enrichment(payload: Any) -> Dict[str, Any]:
    payload = payload or {}
    geo = payload.get("geo", {})
    risk = payload.get("risk", {})
    return {"geo": geo, "risk": risk}


def call_api_with_timeout(payload: Any) -> Dict[str, Any]:
    return {"status": 200, "body": {"message": "ok"}}


def parse_response(payload: Any) -> Dict[str, Any]:
    return (payload or {}).get("body", {})


def guard_threshold(payload: Any) -> List[Tuple[Routing, Any]]:
    should_stop = True
    if should_stop:
        return []
    return [
        (
            Routing(
                target="downstream",
                reason="guard allowed continuation",
            ),
            payload,
        )
    ]


def continue_flow(payload: Any) -> str:
    return "continued"


def split_text(payload):
    payload = payload or ""
    return {"left": payload[::2], "right": payload[1::2]}


def combine_text(payload):
    payload = payload or {}
    return (payload.get("left") or "") + (payload.get("right") or "")
