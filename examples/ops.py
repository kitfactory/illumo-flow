"""Example node callables for illumo_flow demonstrations."""

from __future__ import annotations

from random import random
from typing import Any, Dict

from illumo_flow import Routing


def extract(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"customer_id": 42, "source": "demo"}


def transform(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    raw = payload or {}
    return {**raw, "normalized": True}


def load(context: Dict[str, Any], payload: Any) -> str:
    return "persisted"


def classify(context: Dict[str, Any], payload: Any) -> None:
    confidence = int(random() * 100)
    target = "approve" if confidence > 70 else None
    if target is None:
        target = "manual_review" if confidence < 30 else "reject"
    context.setdefault("routing", {})["classify"] = Routing(next=target, confidence=confidence, reason="demo decision")


def approve(context: Dict[str, Any], payload: Any) -> str:
    return "approved"


def reject(context: Dict[str, Any], payload: Any) -> str:
    return "rejected"


def manual_review(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"id": "TICKET-1", "status": "queued"}


def seed(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"id": 1, "segment": "SMB"}


def enrich_geo(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"country": "JP", "region": "Kanto"}


def enrich_risk(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"score": 0.2, "band": "low"}


def merge_enrichment(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    payload = payload or {}
    geo = payload.get("geo", {})
    risk = payload.get("risk", {})
    return {"geo": geo, "risk": risk}


def call_api_with_timeout(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"status": 200, "body": {"message": "ok"}}


def parse_response(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return (payload or {}).get("body", {})


def guard_threshold(context: Dict[str, Any], payload: Any) -> None:
    should_stop = True
    if should_stop:
        context.setdefault("routing", {})["guard"] = Routing(next=None, confidence=100, reason="threshold triggered")


def continue_flow(context: Dict[str, Any], payload: Any) -> str:
    return "continued"
