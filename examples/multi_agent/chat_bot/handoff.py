"""Helper functions for chat bot handoff and auditing."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def handoff_to_human(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate creating a support ticket when escalation occurs."""

    ticket_id = f"SUPPORT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    log_path = Path("examples/multi_agent/chat_bot/data/handoff_log.jsonl")
    log_entry = {
        "ticket_id": ticket_id,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    return {"ticket_id": ticket_id, "status": "created"}


def audit_conversation(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Record the conversation history for later review."""

    audit_path = Path("examples/multi_agent/chat_bot/data/audit_log.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "history": history,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    return {"status": "logged"}
