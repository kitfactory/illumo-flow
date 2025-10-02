"""Execution policy primitives for illumo-flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Union


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


class PolicyValidationError(ValueError):
    """Raised when a policy definition contains invalid values./ポリシー定義が不正値を含む場合に送出"""

    def __init__(self, errors: Iterable[str]) -> None:
        messages = list(errors)
        super().__init__("; ".join(messages) if messages else "Invalid policy definition")
        self.errors = messages


class PolicyValidator:
    """Validate policy instances and mapping definitions./ポリシーインスタンスや辞書定義を検証する"""

    _ALLOWED_ACTIONS = {"stop", "continue", "goto"}
    _ALLOWED_MODES = {"fixed", "exponential"}

    @classmethod
    def validate(cls, policy: Policy) -> Policy:
        errors: list[str] = []

        if not isinstance(policy.fail_fast, bool):
            errors.append("fail_fast must be a boolean")

        try:
            timeout_seconds = _parse_duration_seconds(policy.timeout)
        except Exception as exc:  # noqa: BLE001 - validation path/検証処理での例外許容
            errors.append(f"timeout is invalid: {exc}")
            timeout_seconds = 0.0
        else:
            if timeout_seconds < 0:
                errors.append("timeout must not be negative")

        if not isinstance(policy.retry, Retry):
            errors.append("retry must be a Retry instance")
        else:
            if policy.retry.max_attempts < 0:
                errors.append("retry.max_attempts must be >= 0")
            if policy.retry.delay < 0:
                errors.append("retry.delay must be >= 0")
            if policy.retry.mode not in cls._ALLOWED_MODES:
                errors.append(
                    "retry.mode must be one of 'fixed' or 'exponential'/retry.mode は fixed か exponential"
                )

        if not isinstance(policy.on_error, OnError):
            errors.append("on_error must be an OnError instance")
        else:
            action = (policy.on_error.action or "").lower()
            if action and action not in cls._ALLOWED_ACTIONS:
                errors.append("on_error.action must be stop|continue|goto")
            if action == "goto" and not policy.on_error.target:
                errors.append("on_error.target is required when action is 'goto'")

        if errors:
            raise PolicyValidationError(errors)
        return policy

    @classmethod
    def normalize(
        cls,
        policy: Optional[Union[Policy, Mapping[str, Any]]],
        *,
        base: Optional[Policy] = None,
    ) -> Policy:
        base_policy = _clone_policy(base) if base is not None else Policy()
        cls.validate(base_policy)

        if policy is None:
            return base_policy
        if isinstance(policy, Policy):
            candidate = _clone_policy(policy)
            return cls.validate(candidate)
        if isinstance(policy, Mapping):
            cls._validate_mapping(policy)
            merged = _merge_policy(base_policy, policy)
            return cls.validate(merged)
        raise PolicyValidationError(["Unsupported policy definition type"])

    @classmethod
    def from_dict(
        cls,
        config: Mapping[str, Any],
        *,
        base: Optional[Policy] = None,
    ) -> Policy:
        if not isinstance(config, Mapping):
            raise PolicyValidationError(["Policy definition must be a mapping"])
        return cls.normalize(config, base=base)

    @classmethod
    def _validate_mapping(cls, config: Mapping[str, Any]) -> None:
        errors: list[str] = []

        if "fail_fast" in config and not isinstance(config["fail_fast"], bool):
            errors.append("fail_fast must be a boolean")

        if "timeout" in config:
            timeout_value = config["timeout"]
            try:
                timeout_seconds = _parse_duration_seconds(timeout_value)
            except Exception as exc:  # noqa: BLE001 - validation only/検証用途
                errors.append(f"timeout is invalid: {exc}")
            else:
                if timeout_seconds < 0:
                    errors.append("timeout must not be negative")

        if "retry" in config:
            retry_value = config["retry"]
            if isinstance(retry_value, Mapping):
                if "max_attempts" in retry_value:
                    try:
                        max_attempts = int(retry_value["max_attempts"])
                    except Exception:  # noqa: BLE001 - validation only/検証用途
                        errors.append("retry.max_attempts must be an integer")
                    else:
                        if max_attempts < 0:
                            errors.append("retry.max_attempts must be >= 0")
                if "delay" in retry_value:
                    delay_candidate = retry_value["delay"]
                    try:
                        delay_seconds = _parse_duration_seconds(delay_candidate)
                    except Exception:  # noqa: BLE001
                        errors.append("retry.delay must be numeric or duration string")
                    else:
                        if delay_seconds < 0:
                            errors.append("retry.delay must be >= 0")
                if "mode" in retry_value:
                    mode_value = str(retry_value["mode"]).lower()
                    if mode_value not in cls._ALLOWED_MODES:
                        errors.append(
                            "retry.mode must be one of 'fixed' or 'exponential'/retry.mode は fixed か exponential"
                        )
            elif isinstance(retry_value, (int, float)):
                if int(retry_value) < 0:
                    errors.append("retry numeric value must be >= 0")
            else:
                errors.append("retry must be mapping or number")

        if "on_error" in config:
            on_error_value = config["on_error"]
            if isinstance(on_error_value, Mapping):
                action_value = str(on_error_value.get("action", "")).lower()
                if action_value and action_value not in cls._ALLOWED_ACTIONS:
                    errors.append("on_error.action must be stop|continue|goto")
                if action_value == "goto" and not on_error_value.get("target"):
                    errors.append("on_error.target is required when action is 'goto'")
            elif isinstance(on_error_value, str):
                action_value = on_error_value.lower()
                if action_value not in cls._ALLOWED_ACTIONS:
                    errors.append("on_error string must be stop|continue|goto")
            else:
                errors.append("on_error must be mapping or string")

        if errors:
            raise PolicyValidationError(errors)


__all__.extend([
    "PolicyValidationError",
    "PolicyValidator",
])
