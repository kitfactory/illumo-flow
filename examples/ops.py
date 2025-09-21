"""Example node callables for illumo_flow demonstrations."""

from __future__ import annotations

from random import random
from typing import Any, Dict

from illumo_flow import Routing


def extract(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    data = {"customer_id": 42, "source": "demo"}
    context.setdefault("outputs", {})["raw"] = data
    return data


def transform(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    raw = payload or context.get("outputs", {}).get("raw", {})
    transformed = {**raw, "normalized": True}
    context.setdefault("outputs", {})["normalized"] = transformed
    return transformed


def load(context: Dict[str, Any], payload: Any) -> str:
    context.setdefault("outputs", {})["persisted"] = True
    return "persisted"


def classify(context: Dict[str, Any], payload: Any) -> None:
    confidence = int(random() * 100)
    target = "approve" if confidence > 70 else None
    if target is None:
        target = "manual_review" if confidence < 30 else "reject"
    context.setdefault("routing", {})["classify"] = Routing(next=target, confidence=confidence, reason="demo decision")


def approve(context: Dict[str, Any], payload: Any) -> str:
    context.setdefault("outputs", {})["decision"] = "approved"
    return "approved"


def reject(context: Dict[str, Any], payload: Any) -> str:
    context.setdefault("outputs", {})["decision"] = "rejected"
    return "rejected"


def manual_review(context: Dict[str, Any], payload: Any) -> str:
    ticket = {"id": "TICKET-1", "status": "queued"}
    context.setdefault("outputs", {})["review_ticket"] = ticket
    return "manual"


def seed(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    customer = {"id": 1, "segment": "SMB"}
    context.setdefault("inputs", {})["customer"] = customer
    return customer


def enrich_geo(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"country": "JP", "region": "Kanto"}


def enrich_risk(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    return {"score": 0.2, "band": "low"}


def merge_enrichment(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    geo = payload.get("geo") if isinstance(payload, dict) else {}
    risk = payload.get("risk") if isinstance(payload, dict) else {}
    profile = {"geo": geo, "risk": risk}
    context.setdefault("outputs", {})["profile"] = profile
    return profile


def call_api_with_timeout(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    response = {"status": 200, "body": {"message": "ok"}}
    context.setdefault("outputs", {})["api_response"] = response
    return response


def parse_response(context: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    body = (payload or {}).get("body", {})
    context.setdefault("outputs", {})["parsed"] = body
    return body


def guard_threshold(context: Dict[str, Any], payload: Any) -> None:
    should_stop = True
    if should_stop:
        context.setdefault("routing", {})["guard"] = Routing(next=None, confidence=100, reason="threshold triggered")


def continue_flow(context: Dict[str, Any], payload: Any) -> str:
    return "continued"
