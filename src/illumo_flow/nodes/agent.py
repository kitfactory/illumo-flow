"""Agent-oriented node implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional

from ..core import (
    FlowError,
    Node,
    NodeConfig,
    _evaluate_expression,
    _parse_target_expression,
    _resolve_scope_mapping,
    _set_to_path,
)
from ..runtime import FlowRuntime, get_llm
from ..tracing import _emit_tracer_event


@dataclass
class AgentRunResult:
    """Normalized LLM invocation outputs."""

    response: Optional[str]
    history: Optional[Iterable[Any]]
    metadata: Optional[Mapping[str, Any]]
    structured: Optional[Any]


class Agent(Node):
    """LLM-backed node that renders prompts and records conversational outputs."""

    DEFAULT_MODEL = "gpt-4.1-nano"

    def __init__(self, *, config: NodeConfig) -> None:
        super().__init__(config=config)
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

    @staticmethod
    def _read_setting(config: NodeConfig, key: str) -> Optional[Any]:
        value = config.setting_value(key)
        return value if value not in {"", None} else None

    # ------------------------------------------------------------------
    def run(self, payload: Any) -> Any:
        context = self.request_context()
        runtime = FlowRuntime.current()
        prompt_text = self._render_template(context, self._prompt_template)
        instructions = self._render_template(context, self._system_prompt)

        tracer = getattr(runtime, "tracer", None)
        if instructions:
            _emit_tracer_event(tracer, "agent_instruction", node_id=self.node_id, text=instructions)
        if prompt_text:
            _emit_tracer_event(tracer, "agent_input", node_id=self.node_id, text=prompt_text)

        llm = get_llm(self._provider, self._model, base_url=self._base_url)
        result = self._invoke_llm(llm, prompt_text, instructions=instructions)
        normalized = self._normalize_result(result)

        if normalized.response:
            _emit_tracer_event(tracer, "agent_response", node_id=self.node_id, text=normalized.response)

        self._store_outputs(context, normalized)
        return normalized.response

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
        if responses is not None:
            create = getattr(responses, "create", None)
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

        if hasattr(value, "output_text"):
            output_text = getattr(value, "output_text")
            if isinstance(output_text, Iterable):
                output_list = list(output_text)
                if output_list:
                    response_text = str(output_list[0])
            else:
                response_text = str(output_text)

        if response_text is None and hasattr(value, "text"):
            response_text = str(getattr(value, "text"))

        if response_text is None and isinstance(value, Mapping):
            response_text = str(value.get("response") or value.get("content") or "")

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
    def _store_outputs(self, context: MutableMapping[str, Any], result: AgentRunResult) -> None:
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

        self._store_slot(context, bucket, "response", self._output_path, result.response, append_entry)
        self._store_slot(context, bucket, "history", self._history_path, result.history, append_entry)
        self._store_slot(context, bucket, "metadata", self._metadata_path, result.metadata, append_entry)
        self._store_slot(context, bucket, "structured", self._structured_path, result.structured, append_entry)

    def _store_slot(
        self,
        context: MutableMapping[str, Any],
        bucket: MutableMapping[str, Any],
        key: str,
        path: Optional[str],
        value: Any,
        default_writer: Callable[[str, Any], None],
    ) -> None:
        if value is None:
            return
        if path:
            scope, rel = _parse_target_expression(path)
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
            return str(_evaluate_expression(context, template))
        except Exception:
            return template
