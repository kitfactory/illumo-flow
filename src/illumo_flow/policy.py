"""Execution policy primitives for illumo-flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional


@dataclass
class Retry:
    max_attempts: int = 0
    delay: float = 0.0
    mode: str = "fixed"


@dataclass
class OnError:
    action: str = "stop"
    target: Optional[str] = None


@dataclass
class Policy:
    fail_fast: bool = True
    timeout: str = "0s"
    retry: Retry = Retry()
    on_error: OnError = OnError()


def _parse_duration_seconds(value: str) -> float:
    text = str(value or "0").strip().lower()
    if not text or text == "0" or text == "0s":
        return 0.0
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    for suffix, factor in multipliers.items():
        if text.endswith(suffix):
            number = float(text[: -len(suffix)] or 0)
            return max(number * factor, 0.0)
    return max(float(text), 0.0)


def _build_retry(base: Retry, value: Any) -> Retry:
    if isinstance(value, Retry):
        return value
    if isinstance(value, (int, float)):
        return Retry(max_attempts=int(value), delay=base.delay, mode=base.mode)
    if isinstance(value, Mapping):
        max_attempts = int(value.get("max_attempts", base.max_attempts))
        delay_value = value.get("delay", base.delay)
        if isinstance(delay_value, str):
            delay = _parse_duration_seconds(delay_value)
        else:
            delay = float(delay_value)
        mode = str(value.get("mode", base.mode or "fixed"))
        if mode not in {"fixed", "exponential"}:
            mode = "fixed"
        return Retry(max_attempts=max_attempts, delay=max(delay, 0.0), mode=mode)
    return base


def _build_on_error(base: OnError, value: Any) -> OnError:
    if isinstance(value, OnError):
        return value
    if isinstance(value, str):
        return OnError(action=value, target=None)
    if isinstance(value, Mapping):
        action = str(value.get("action", base.action or "stop"))
        target = value.get("target", base.target)
        return OnError(action=action, target=target)
    return base


def _clone_policy(policy: Policy) -> Policy:
    return Policy(
        fail_fast=policy.fail_fast,
        timeout=policy.timeout,
        retry=Retry(
            max_attempts=policy.retry.max_attempts,
            delay=policy.retry.delay,
            mode=policy.retry.mode,
        ),
        on_error=OnError(action=policy.on_error.action, target=policy.on_error.target),
    )


def _merge_policy(base: Policy, override_value: Any) -> Policy:
    if override_value is None:
        return base
    override = override_value
    if isinstance(override_value, Policy):
        override = {
            "fail_fast": override_value.fail_fast,
            "timeout": override_value.timeout,
            "retry": override_value.retry,
            "on_error": override_value.on_error,
        }
    if not isinstance(override, Mapping):
        return base

    fail_fast = bool(override.get("fail_fast", base.fail_fast))
    timeout = str(override.get("timeout", base.timeout))
    retry = _build_retry(base.retry, override.get("retry")) if "retry" in override else base.retry
    on_error = _build_on_error(base.on_error, override.get("on_error")) if "on_error" in override else base.on_error
    return Policy(fail_fast=fail_fast, timeout=timeout, retry=retry, on_error=on_error)


def _record_node_error(context: MutableMapping[str, Any], node_id: str, exc: BaseException) -> None:
    error_record = {
        "node_id": node_id,
        "exception": exc.__class__.__name__,
        "message": str(exc),
    }
    context.setdefault("errors", []).append(error_record)
    context["failed_node_id"] = node_id
    context["failed_exception_type"] = exc.__class__.__name__
    context["failed_message"] = str(exc)
    context.setdefault("steps", []).append({"node_id": node_id, "status": "failed", "message": str(exc)})


__all__ = [
    "Policy",
    "Retry",
    "OnError",
    "_parse_duration_seconds",
    "_clone_policy",
    "_merge_policy",
    "_record_node_error",
]

