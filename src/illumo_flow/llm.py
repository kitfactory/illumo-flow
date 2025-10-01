"""LLM client helpers for illumo-flow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit


try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # noqa: BLE001 - optional import failure
    OpenAI = None  # type: ignore[assignment]

def _default_llm_factory(
    *,
    provider: Optional[str],
    model: str,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    resolved_provider = _resolve_provider(provider, model, base_url, kwargs)
    builder = _PROVIDER_BUILDERS.get(resolved_provider)
    if builder is None:
        raise ValueError(f"Unsupported LLM provider '{resolved_provider}'")
    normalized_base_url = _determine_base_url(resolved_provider, base_url)
    return builder(model=model, base_url=normalized_base_url, options=kwargs)


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


def _determine_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    if base_url is None:
        return None if provider == "openai" else None
    if provider == "openai":
        return base_url.rstrip("/") or None
    return _normalize_llm_base_url(base_url)


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


def _ensure_openai() -> Any:
    if OpenAI is None:
        class _FallbackOpenAI:  # pragma: no cover - exercised via unit tests only
            def __init__(self, **kwargs: Any) -> None:
                self._kwargs = dict(kwargs)
                self.base_url = kwargs.get("base_url")
                self.responses = SimpleNamespace(create=self._not_available)
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._not_available))

            def _not_available(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("OpenAI SDK is required for actual LLM calls")

        return _FallbackOpenAI
    return OpenAI


def _set_metadata(client: Any, *, provider: str, model: str, base_url: Optional[str]) -> Any:
    setattr(client, "_illumo_provider", provider)
    setattr(client, "_illumo_model", model)
    if base_url is not None and not getattr(client, "base_url", None):
        setattr(client, "base_url", base_url)
    return client


def _build_openai_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    client = None
    openai_cls = _ensure_openai()
    kw = dict(options)
    if base_url:
        kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="openai", model=model, base_url=base_url)


def _build_anthropic_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    if base_url is None:
        raise ValueError("Anthropic provider requires a base_url for the OpenAI-compatible endpoint")
    openai_cls = _ensure_openai()
    kw = dict(options)
    kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="anthropic", model=model, base_url=base_url)


def _build_google_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    if base_url is None:
        raise ValueError("Google provider requires a base_url for the OpenAI-compatible endpoint")
    openai_cls = _ensure_openai()
    kw = dict(options)
    kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="google", model=model, base_url=base_url)


def _build_lmstudio_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    if base_url is None:
        raise ValueError("LMStudio provider requires a base_url for the OpenAI-compatible endpoint")
    openai_cls = _ensure_openai()
    kw = dict(options)
    kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="lmstudio", model=model, base_url=base_url)


def _build_ollama_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    if base_url is None:
        raise ValueError("Ollama provider requires a base_url for the OpenAI-compatible endpoint")
    openai_cls = _ensure_openai()
    kw = dict(options)
    kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="ollama", model=model, base_url=base_url)


def _build_openrouter_client(*, model: str, base_url: Optional[str], options: Mapping[str, Any]) -> Any:
    if base_url is None:
        raise ValueError("OpenRouter provider requires a base_url for the OpenAI-compatible endpoint")
    openai_cls = _ensure_openai()
    kw = dict(options)
    kw["base_url"] = base_url
    client = openai_cls(**kw)
    return _set_metadata(client, provider="openrouter", model=model, base_url=base_url)


_PROVIDER_BUILDERS: Dict[str, Callable[..., Any]] = {
    "openai": _build_openai_client,
    "anthropic": _build_anthropic_client,
    "google": _build_google_client,
    "lmstudio": _build_lmstudio_client,
    "ollama": _build_ollama_client,
    "openrouter": _build_openrouter_client,
}


__all__ = [
    "_default_llm_factory",
    "_normalize_llm_base_url",
    "_apply_normalized_base_url",
    "_determine_base_url",
    "_resolve_provider",
]
