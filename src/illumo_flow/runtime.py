"""Runtime configuration helpers for illumo-flow."""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Optional

from .llm import _apply_normalized_base_url, _default_llm_factory, _normalize_llm_base_url
from .policy import Policy
from .tracing import ConsoleTracer


class FlowRuntime:
    """Execution-time configuration container for Flow concerns."""

    __slots__ = ("tracer", "policy", "llm_factory")
    _global: ClassVar[Optional["FlowRuntime"]] = None

    def __init__(
        self,
        *,
        tracer: Any = None,
        policy: Optional[Policy] = None,
        llm_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.tracer = tracer
        self.policy = policy or Policy()
        self.llm_factory = llm_factory

    @classmethod
    def default(cls) -> "FlowRuntime":
        return cls(tracer=ConsoleTracer(), policy=Policy())

    @classmethod
    def configure(
        cls,
        *,
        tracer: Any = None,
        policy: Optional[Policy] = None,
        llm_factory: Optional[Callable[..., Any]] = None,
    ) -> "FlowRuntime":
        cls._global = cls(tracer=tracer, policy=policy or Policy(), llm_factory=llm_factory)
        return cls._global

    @classmethod
    def current(cls) -> "FlowRuntime":
        if cls._global is None:
            cls._global = cls.default()
        return cls._global

    def get_llm(self, provider: Optional[str], model: str, **kwargs: Any) -> Any:
        factory = self.llm_factory or _default_llm_factory
        return factory(provider=provider, model=model, **kwargs)


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
    "get_llm",
]
