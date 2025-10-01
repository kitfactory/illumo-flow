"""Agent-oriented node implementations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from ..core import (
    FlowError,
    Node,
    NodeConfig,
    Routing,
    RoutingNode,
    _evaluate_expression,
    _parse_target_expression,
    _resolve_scope_mapping,
    _set_to_path,
)
from ..runtime import get_llm
from ..tracing import emit_event


class AgentRunResult:
    """Normalized output returned from an LLM invocation."""

    __slots__ = ("response", "history", "metadata", "structured")

    def __init__(
        self,
        response: Optional[str],
        history: Optional[Iterable[Any]],
        metadata: Optional[Mapping[str, Any]],
        structured: Optional[Any],
    ) -> None:
        self.response = response
        self.history = history
        self.metadata = metadata
        self.structured = structured


class AgentMixin:
    """Shared behaviour for Agent variants."""

    DEFAULT_MODEL = "gpt-4.1-nano"

    def __init__(self, *, config: NodeConfig) -> None:
        self._provider: Optional[str] = self._read_setting(config, "provider")
        self._model: str = self._read_setting(config, "model") or self.DEFAULT_MODEL
        self._base_url: Optional[str] = self._read_setting(config, "base_url")
        self._system_prompt: Optional[str] = self._read_setting(config, "system")
        self._prompt_template: Optional[str] = self._read_setting(config, "prompt")
        self._tools: Optional[Iterable[Any]] = self._read_setting(config, "tools")
        self._output_path: Optional[str] = self._read_setting(config, "output_path")
        self._history_path: Optional[str] = self._read_setting(config, "history_path")
        self._metadata_path: Optional[str] = self._read_setting(config, "metadata_path")
        self._structured_path: Optional[str] = self._read_setting(config, "structured_path")

    # ------------------------------------------------------------------
    @staticmethod
    def _read_setting(config: NodeConfig, key: str) -> Optional[Any]:
        value = config.setting_value(key)
        if value is None:
            return None
        if isinstance(value, str) and not value:
            return None
        return value

    # ------------------------------------------------------------------
    def _invoke(
        self,
        context: MutableMapping[str, Any],
        *,
        prompt_override: Optional[str] = None,
        system_override: Optional[str] = None,
    ) -> Tuple[AgentRunResult, str]:
        instructions = self._render_template(context, system_override if system_override is not None else self._system_prompt)
        prompt_text = self._render_template(context, prompt_override if prompt_override is not None else self._prompt_template)

        if instructions:
            emit_event("agent_instruction", message=instructions, attributes={"node_id": self.node_id})
        if prompt_text:
            emit_event("agent_input", message=prompt_text, attributes={"node_id": self.node_id})

        llm = get_llm(self._provider, self._model, base_url=self._base_url)
        raw_result = self._invoke_llm(llm, prompt_text, instructions=instructions)
        normalized = self._normalize_result(raw_result)

        if normalized.response:
            emit_event("agent_response", message=normalized.response, attributes={"node_id": self.node_id})

        timestamp = self._store_outputs(context, normalized)
        return normalized, timestamp

    # ------------------------------------------------------------------
    def _invoke_llm(
        self,
        llm: Any,
        prompt_text: Optional[str],
        *,
        instructions: Optional[str],
    ) -> Any:
        request_payload: Dict[str, Any] = {"model": self._model}
        if instructions:
            request_payload["instructions"] = instructions
        if prompt_text is not None:
            request_payload["input"] = prompt_text
        if self._tools:
            request_payload["tools"] = list(self._tools)

        responses = getattr(llm, "responses", None)
        create = getattr(responses, "create", None) if responses is not None else None
        if callable(create):
            return create(**request_payload)

        chat = getattr(llm, "chat", None)
        completions = getattr(chat, "completions", None) if chat is not None else None
        chat_create = getattr(completions, "create", None)
        if callable(chat_create):
            messages = []
            if instructions:
                messages.append({"role": "system", "content": instructions})
            user_content = prompt_text or ""
            messages.append({"role": "user", "content": user_content})
            chat_payload = {"model": self._model, "messages": messages}
            if self._tools:
                chat_payload["tools"] = list(self._tools)
            return chat_create(**chat_payload)

        raise FlowError("LLM client does not support responses or chat completions API")

    # ------------------------------------------------------------------
    def _normalize_result(self, value: Any) -> AgentRunResult:
        response_text: Optional[str] = None
        history: Optional[Iterable[Any]] = None
        metadata: Optional[Mapping[str, Any]] = None
        structured: Optional[Any] = None

        candidates = (
            getattr(value, "output_text", None),
            getattr(value, "text", None),
            getattr(value, "content", None),
        )
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, str):
                response_text = candidate
                break
            if isinstance(candidate, Iterable):
                items = list(candidate)
                if items:
                    response_text = str(items[0])
                    break

        if response_text is None and isinstance(value, Mapping):
            for key in ("response", "content", "text"):
                if key in value and value[key]:
                    response_text = str(value[key])
                    break

        if hasattr(value, "messages"):
            history = getattr(value, "messages")
        elif isinstance(value, Mapping) and "messages" in value:
            history = value.get("messages")

        if hasattr(value, "metadata"):
            metadata = getattr(value, "metadata")
        elif isinstance(value, Mapping) and "metadata" in value:
            metadata = value.get("metadata")

        if hasattr(value, "structured_output"):
            structured = getattr(value, "structured_output")
        elif isinstance(value, Mapping) and "structured" in value:
            structured = value.get("structured")

        return AgentRunResult(
            response=response_text,
            history=history,
            metadata=metadata,
            structured=structured,
        )

    # ------------------------------------------------------------------
    def _store_outputs(self, context: MutableMapping[str, Any], result: AgentRunResult) -> str:
        bucket = context.setdefault("agents", {}).setdefault(self.node_id, {})
        timestamp = datetime.utcnow().isoformat()

        def append_entry(key: str, value: Any) -> None:
            if value is None:
                return
            entry = {"timestamp": timestamp, "value": value}
            existing = bucket.get(key)
            if existing is None:
                bucket[key] = entry
            elif isinstance(existing, list):
                existing.append(entry)
            else:
                bucket[key] = [existing, entry]

        self._store_slot(
            context=context,
            bucket=bucket,
            key="response",
            target_path=self._output_path,
            value=result.response,
            default_writer=append_entry,
        )
        self._store_slot(
            context=context,
            bucket=bucket,
            key="history",
            target_path=self._history_path,
            value=result.history,
            default_writer=append_entry,
        )
        self._store_slot(
            context=context,
            bucket=bucket,
            key="metadata",
            target_path=self._metadata_path,
            value=result.metadata,
            default_writer=append_entry,
        )
        self._store_slot(
            context=context,
            bucket=bucket,
            key="structured",
            target_path=self._structured_path,
            value=result.structured,
            default_writer=append_entry,
        )
        return timestamp

    # ------------------------------------------------------------------
    def _store_slot(
        self,
        context: MutableMapping[str, Any],
        bucket: MutableMapping[str, Any],
        *,
        key: str,
        target_path: Optional[str],
        value: Any,
        default_writer: Callable[[str, Any], None],
    ) -> None:
        if value is None:
            return
        if target_path:
            scope, rel = _parse_target_expression(target_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, value)
        else:
            default_writer(key, value)

    # ------------------------------------------------------------------
    def _render_template(
        self,
        context: MutableMapping[str, Any],
        template: Optional[str],
    ) -> Optional[str]:
        if not template:
            return None
        try:
            rendered = _evaluate_expression(context, template)
        except Exception:
            rendered = template
        return str(rendered) if rendered is not None else None


class Agent(AgentMixin, Node):
    """Standard LLM agent node."""

    def __init__(self, *, config: NodeConfig) -> None:
        Node.__init__(self, config=config)
        AgentMixin.__init__(self, config=config)

    def run(self, payload: Any) -> Any:
        context = self.request_context()
        result, _ = self._invoke(context)
        return result.response


class RouterAgent(AgentMixin, RoutingNode):
    """Routing node driven by an LLM decision."""

    def __init__(self, *, config: NodeConfig) -> None:
        RoutingNode.__init__(self, config=config)
        AgentMixin.__init__(self, config=config)
        raw_choices = self._read_setting(config, "choices")
        if not raw_choices or not isinstance(raw_choices, Iterable):
            raise FlowError("RouterAgent requires a 'choices' iterable in settings")
        self._choices = [str(choice) for choice in raw_choices]

    def run(self, payload: Any) -> Routing:
        context = self.request_context()
        prompt_override = self._prompt_template or ""
        choice_clause = ", ".join(self._choices)
        prompt_override = (
            f"{prompt_override}\n\nChoose exactly one of: {choice_clause}."
            if prompt_override
            else f"Choose exactly one of: {choice_clause}."
        )

        normalized, timestamp = self._invoke(context, prompt_override=prompt_override)
        decision = self._extract_choice(normalized.response)
        reason = normalized.response

        self._store_router_outputs(context, decision, reason, timestamp)
        return Routing(target=decision, reason=reason)

    def _extract_choice(self, response_text: Optional[str]) -> str:
        if not response_text:
            raise FlowError("RouterAgent could not determine a decision from an empty response")
        lowered = response_text.lower()
        for choice in self._choices:
            if choice.lower() in lowered:
                return choice
        # fallback to first token if matches exactly
        candidate = response_text.strip().split()[0]
        for choice in self._choices:
            if choice.lower() == candidate.lower():
                return choice
        raise FlowError("RouterAgent response did not contain any configured choice")

    def _store_router_outputs(
        self,
        context: MutableMapping[str, Any],
        decision: str,
        reason: Optional[str],
        timestamp: str,
    ) -> None:
        records = context.setdefault("routing", {}).setdefault(self.node_id, [])
        record = {"timestamp": timestamp, "target": decision}
        if reason:
            record["reason"] = reason
        records.append(record)

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, decision)

        if self._metadata_path and reason is not None:
            scope, rel = _parse_target_expression(self._metadata_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, reason)


class EvaluationAgent(AgentMixin, Node):
    """LLM-backed evaluator that records numeric scores and JSON details."""

    def __init__(self, *, config: NodeConfig) -> None:
        Node.__init__(self, config=config)
        AgentMixin.__init__(self, config=config)
        self._target: Optional[str] = self._read_setting(config, "target")

    def run(self, payload: Any) -> Any:
        context = self.request_context()
        prompt_override = self._prompt_template
        if self._target:
            try:
                target_value = _evaluate_expression(context, self._target)
            except Exception as exc:
                raise FlowError("EvaluationAgent failed to resolve target expression") from exc
            target_text = "" if target_value is None else str(target_value)
            if prompt_override:
                prompt_override = f"{prompt_override}\n\nTarget:\n{target_text}"
            else:
                prompt_override = (
                    "Evaluate the following content and respond with JSON containing "
                    "fields 'score' and 'reasons':\n"
                    f"{target_text}"
                )

        normalized, timestamp = self._invoke(context, prompt_override=prompt_override)
        score, reasons, structured = self._parse_evaluation(normalized)

        self._store_evaluation(context, score, reasons, structured, timestamp)
        return score

    def _parse_evaluation(self, result: AgentRunResult) -> Tuple[Any, Optional[str], Optional[Any]]:
        structured_payload = result.structured
        reasons: Optional[str] = None
        score: Any = result.response

        if structured_payload is None and result.response:
            try:
                structured_payload = json.loads(result.response)
            except Exception:
                structured_payload = None

        if isinstance(structured_payload, Mapping):
            if "score" in structured_payload:
                score = structured_payload.get("score")
            reasons = structured_payload.get("reasons") or structured_payload.get("reason")
        elif isinstance(score, str):
            stripped = score.strip()
            if stripped.isdigit():
                score = int(stripped)

        return score, reasons, structured_payload

    def _store_evaluation(
        self,
        context: MutableMapping[str, Any],
        score: Any,
        reasons: Optional[str],
        structured: Optional[Any],
        timestamp: str,
    ) -> None:
        metrics_bucket = context.setdefault("metrics", {}).setdefault(self.node_id, [])
        entry: Dict[str, Any] = {"timestamp": timestamp, "score": score}
        if reasons:
            entry["reasons"] = reasons
        if structured is not None:
            entry["structured"] = structured
        metrics_bucket.append(entry)

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, score)

        if self._metadata_path and reasons is not None:
            scope, rel = _parse_target_expression(self._metadata_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, reasons)

        if self._structured_path and structured is not None:
            scope, rel = _parse_target_expression(self._structured_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, structured)
