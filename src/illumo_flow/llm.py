"""LLM client helpers for illumo-flow."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit


try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # noqa: BLE001 - optional import failure
    OpenAI = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from anthropic import Anthropic
except Exception:  # noqa: BLE001 - optional import failure
    Anthropic = None  # type: ignore[assignment]


def _try_import(name: str) -> Any:
    """Best-effort dynamic import returning ``None`` on failure."""

    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 - optional import failure
        return None


_GOOGLE_GENAI = _try_import("google.generativeai")


@dataclass(slots=True)
class SimpleLLMClient:
    """Lightweight handle that keeps provider metadata and optional SDK client."""

    provider: str
    model: str
    base_url: Optional[str] = None
    client: Any = None

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
            history = list(conversation or []) + [
                {"role": "assistant", "content": response}
            ]
            result["history"] = history
        return result


def _default_llm_factory(
    *,
    provider: Optional[str],
    model: str,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> SimpleLLMClient:
    resolved_provider = _resolve_provider(provider, model, base_url, kwargs)
    builder = _PROVIDER_BUILDERS.get(resolved_provider, _build_openai_client)
    return builder(model=model, base_url=base_url, options=kwargs)


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


def _resolve_provider(
    provider: Optional[str],
    model: str,
    base_url: Optional[str],
    options: Mapping[str, Any],
) -> str:
    if provider:
        return provider.lower()

    name = (model or "").lower()
    host = (base_url or "").lower()

    if "claude" in name or "anthropic" in name:
        return "anthropic"
    if any(token in name for token in ("gemini", "text-bison", "chat-bison", "palm")):
        return "google"
    if "ollama" in host or ":11434" in host or name.startswith("ollama/"):
        return "ollama"
    if "openrouter" in host or "openrouter" in name:
        return "openrouter"
    if "lmstudio" in host or ":1234" in host or "/gpt-oss" in name:
        return "lmstudio"
    if options.get("provider"):
        return str(options["provider"]).lower()
    return "openai"


def _build_openai_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    client = None
    if OpenAI is not None:
        client = OpenAI(base_url=base_url, **options)
    return SimpleLLMClient(provider="openai", model=model, base_url=base_url, client=client)


def _build_anthropic_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    client = Anthropic(**options) if Anthropic is not None else None
    return SimpleLLMClient(provider="anthropic", model=model, base_url=base_url, client=client)


def _build_google_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    client = None
    if _GOOGLE_GENAI is not None:
        _GOOGLE_GENAI.configure(**{k: v for k, v in options.items() if k != "provider"})
        client = _GOOGLE_GENAI
    return SimpleLLMClient(provider="google", model=model, base_url=base_url, client=client)


def _build_lmstudio_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    return SimpleLLMClient(provider="lmstudio", model=model, base_url=base_url, client=None)


def _build_ollama_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    return SimpleLLMClient(provider="ollama", model=model, base_url=base_url, client=None)


def _build_openrouter_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> SimpleLLMClient:
    return SimpleLLMClient(provider="openrouter", model=model, base_url=base_url, client=None)


_PROVIDER_BUILDERS: Dict[str, Callable[..., SimpleLLMClient]] = {
    "openai": _build_openai_client,
    "anthropic": _build_anthropic_client,
    "google": _build_google_client,
    "lmstudio": _build_lmstudio_client,
    "ollama": _build_ollama_client,
    "openrouter": _build_openrouter_client,
}


__all__ = [
    "SimpleLLMClient",
    "_default_llm_factory",
    "_normalize_llm_base_url",
    "_apply_normalized_base_url",
    "_resolve_provider",
]
