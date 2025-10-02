"""Runtime configuration helpers for illumo-flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Mapping, MutableMapping, Optional, Union

from .llm import _apply_normalized_base_url, _default_llm_factory, _normalize_llm_base_url
from .policy import Policy, PolicyValidator
from .tracing import ConsoleTracer

if TYPE_CHECKING:  # pragma: no cover - typing helper/型ヒント専用
    from .core import Flow


@dataclass
class RuntimeExecutionReport:
    """Summary object capturing flow execution failure details./フロー実行の失敗詳細を保持するサマリ"""

    trace_id: Optional[str] = None
    failed_node_id: Optional[str] = None
    summary: Optional[str] = None
    policy_snapshot: Mapping[str, Any] = field(default_factory=dict)
    context_digest: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Mapping[str, Any]:
        """Return a JSON-serialisable mapping./JSON 化しやすい辞書を返す"""

        return {
            "trace_id": self.trace_id,
            "failed_node_id": self.failed_node_id,
            "summary": self.summary,
            "policy_snapshot": dict(self.policy_snapshot),
            "context_digest": dict(self.context_digest),
        }


class FlowRuntime:
    """Execution-time configuration container for Flow concerns."""

    __slots__ = ("tracer", "policy", "llm_factory")
    _global: ClassVar[Optional["FlowRuntime"]] = None

    def __init__(
        self,
        *,
        tracer: Any = None,
        policy: Optional[Union[Policy, Mapping[str, Any]]] = None,
        llm_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.tracer = tracer
        self.policy = PolicyValidator.normalize(policy, base=None)
        self.llm_factory = llm_factory

    @classmethod
    def default(cls) -> "FlowRuntime":
        return cls(tracer=ConsoleTracer(), policy=Policy())

    @classmethod
    def configure(
        cls,
        *,
        tracer: Any = None,
        policy: Optional[Union[Policy, Mapping[str, Any]]] = None,
        llm_factory: Optional[Callable[..., Any]] = None,
    ) -> "FlowRuntime":
        cls._global = cls(tracer=tracer, policy=policy, llm_factory=llm_factory)
        return cls._global

    @classmethod
    def current(cls) -> "FlowRuntime":
        if cls._global is None:
            cls._global = cls.default()
        return cls._global

    def get_llm(self, provider: Optional[str], model: str, **kwargs: Any) -> Any:
        factory = self.llm_factory or _default_llm_factory
        return factory(provider=provider, model=model, **kwargs)

    def run(
        self,
        flow: "Flow",
        context: Optional[MutableMapping[str, Any]] = None,
        *,
        user_input: Any = None,
        report: Optional[RuntimeExecutionReport] = None,
    ) -> MutableMapping[str, Any]:
        previous = self.__class__._global
        self.__class__._global = self
        try:
            return flow.run(context, user_input=user_input, report=report)
        finally:
            if previous is None:
                self.__class__._global = None
            else:
                self.__class__._global = previous


def get_llm(
    provider: Optional[str],
    model: str,
    *,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    runtime = FlowRuntime.current()
    llm = runtime.get_llm(provider, model, base_url=base_url, **kwargs)
    if base_url:
        provider_marker = getattr(llm, "_illumo_provider", (provider or "openai").lower())
        if provider_marker == "openai":
            normalized_url = base_url.rstrip("/")
        else:
            normalized_url = _normalize_llm_base_url(base_url)
        if normalized_url:
            _apply_normalized_base_url(llm, normalized_url)
    return llm


__all__ = [
    "FlowRuntime",
    "RuntimeExecutionReport",
    "get_llm",
]
