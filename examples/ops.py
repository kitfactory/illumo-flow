"""Example node callables for illumo_flow demonstrations."""

from __future__ import annotations

from random import random
from typing import Any, Dict


def extract(payload: Any) -> Dict[str, Any]:
    return {"customer_id": 42, "source": "demo"}


def transform(payload: Any, ctx) -> Dict[str, Any]:
    raw = payload or {}
    return {**raw, "normalized": True}


def load(payload: Any, ctx) -> str:
    return "persisted"


def classify(payload: Any, ctx) -> None:
    confidence = int(random() * 100)
    target = "approve" if confidence > 70 else None
    if target is None:
        target = "manual_review" if confidence < 30 else "reject"
    ctx.write("$ctx.metrics.score", confidence)
    ctx.route(next=target, confidence=confidence, reason="demo decision")


def approve(payload: Any, ctx) -> str:
    return "approved"


def reject(payload: Any, ctx) -> str:
    return "rejected"


def manual_review(payload: Any, ctx) -> Dict[str, Any]:
    return {"id": "TICKET-1", "status": "queued"}


def seed(payload: Any, ctx) -> Dict[str, Any]:
    return {"id": 1, "segment": "SMB"}


def enrich_geo(payload: Any, ctx) -> Dict[str, Any]:
    return {"country": "JP", "region": "Kanto"}


def enrich_risk(payload: Any, ctx) -> Dict[str, Any]:
    return {"score": 0.2, "band": "low"}


def merge_enrichment(payload: Any, ctx) -> Dict[str, Any]:
    payload = payload or {}
    geo = payload.get("geo", {})
    risk = payload.get("risk", {})
    return {"geo": geo, "risk": risk}


def call_api_with_timeout(payload: Any, ctx) -> Dict[str, Any]:
    return {"status": 200, "body": {"message": "ok"}}


def parse_response(payload: Any, ctx) -> Dict[str, Any]:
    return (payload or {}).get("body", {})


def guard_threshold(payload: Any, ctx) -> None:
    should_stop = True
    if should_stop:
        ctx.route(next=None, confidence=100, reason="threshold triggered")


def continue_flow(payload: Any, ctx) -> str:
    return "continued"


def split_text(payload, ctx):
    payload = payload or ""
    return {"left": payload[::2], "right": payload[1::2]}


def combine_text(payload, ctx):
    payload = payload or {}
    return (payload.get("left") or "") + (payload.get("right") or "")
