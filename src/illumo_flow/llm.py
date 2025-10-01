"""LLM client helpers for illumo-flow."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit


class SimpleLLMClient:
    """Minimal pluggable LLM client used for default execution."""

    def __init__(
        self,
        *,
        provider: Optional[str],
        model: str,
        base_url: Optional[str] = None,
        **_: Any,
    ) -> None:
        self.provider = provider or "openai"
        self.model = model
        self.base_url = base_url

    def complete(
        self,
        prompt: str,
        *,
        conversation: Optional[Sequence[Mapping[str, Any]]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        **_: Any,
    ) -> dict[str, Any]:
        history_preview = conversation[-1]["content"] if conversation else None
        response = prompt if prompt is not None else ""
        meta: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
        }
        if self.base_url:
            meta["base_url"] = self.base_url
        if metadata:
            meta.update(dict(metadata))
        result: dict[str, Any] = {
            "response": response,
            "metadata": meta,
        }
        if history_preview is not None:
            result["history"] = list(conversation or []) + [
                {"role": "assistant", "content": response}
            ]
        return result


def _default_llm_factory(
    *,
    provider: Optional[str],
    model: str,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> SimpleLLMClient:
    return SimpleLLMClient(provider=provider, model=model, base_url=base_url, **kwargs)


def _normalize_llm_base_url(base_url: Optional[str]) -> Optional[str]:
    if not base_url:
        return None

    parsed = urlsplit(base_url)
    path = (parsed.path or "").rstrip("/")

    if not path:
        normalized_path = "/v1"
    elif "/v1" in path:
        normalized_path = path
    else:
        normalized_path = f"{path}/v1"

    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path.lstrip('/')}"

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            normalized_path,
            parsed.query,
            parsed.fragment,
        )
    )


def _apply_normalized_base_url(llm: Any, base_url: str) -> None:
    normalized = base_url.rstrip("/")
    if hasattr(llm, "base_url"):
        try:
            setattr(llm, "base_url", normalized)
        except Exception:
            pass
    client = getattr(llm, "client", None)
    if client is not None and hasattr(client, "base_url"):
        try:
            client.base_url = normalized
        except Exception:
            pass


__all__ = [
    "SimpleLLMClient",
    "_default_llm_factory",
    "_normalize_llm_base_url",
    "_apply_normalized_base_url",
]

