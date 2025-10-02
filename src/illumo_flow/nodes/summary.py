"""Nodes for summarising flow results."""

from __future__ import annotations

from typing import Any, Dict, List, MutableMapping, Optional

from ..core import Node, NodeConfig, _parse_target_expression, _resolve_scope_mapping, _set_to_path


class SummaryAgent(Node):
    """Compile workspace, test, and review outcomes into human-readable summaries."""

    def __init__(self, *, config: NodeConfig) -> None:
        super().__init__(config=config)
        self._output_path = config.setting_value("output_path")
        self._structured_path = config.setting_value("structured_path")

    def run(self, payload: Any) -> Dict[str, Any]:  # type: ignore[override]
        context = self.request_context()

        workspace_files = context.get("workspace", {}).get("files", [])
        tests_result = context.get("tests", {}).get("results", {})
        review_summary = context.get("review", {})

        report_lines: List[str] = []

        if workspace_files:
            report_lines.append("### Files")
            for entry in workspace_files:
                path = entry.get("path")
                status = entry.get("status")
                report_lines.append(f"- {path}: {status}")

        if tests_result:
            status = "PASS" if tests_result.get("returncode") == 0 else "FAIL"
            report_lines.append("### Tests")
            report_lines.append(f"- Status: {status}")
            if "command" in tests_result:
                cmd_display = " ".join(str(part) for part in tests_result["command"])
                report_lines.append(f"- Command: {cmd_display}")
            if tests_result.get("stdout"):
                report_lines.append("- Stdout snippet:\n" + tests_result["stdout"].strip()[:200])
            if tests_result.get("stderr"):
                report_lines.append("- Stderr snippet:\n" + tests_result["stderr"].strip()[:200])

        if review_summary:
            report_lines.append("### Review")
            status = review_summary.get("status")
            if status:
                report_lines.append(f"- Status: {status}")
            if review_summary.get("summary"):
                report_lines.append(f"- Notes: {review_summary['summary']}")

        if not report_lines:
            report_lines.append("No updates were recorded.")

        report_text = "\n".join(report_lines)
        structured = {
            "files": workspace_files,
            "tests": tests_result,
            "review": review_summary,
        }

        summary_bucket = context.setdefault("summary", {})
        summary_bucket["report"] = report_text
        summary_bucket["structured"] = structured

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, report_text)

        if self._structured_path:
            scope, rel = _parse_target_expression(self._structured_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, structured)

        return {"report": report_text, "structured": structured}


__all__ = ["SummaryAgent"]
