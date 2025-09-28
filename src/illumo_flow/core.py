"""Core Flow orchestration primitives."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple, Union


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_EXPRESSION_PREFIXES = ("ctx", "payload", "joins", "env")


@dataclass(frozen=True)
class Routing:
    """Routing outcome for a single downstream target."""

    target: str
    confidence: Optional[float] = None
    reason: Optional[str] = None

    def to_context(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {"target": self.target}
        if self.confidence is not None:
            record["confidence"] = self.confidence
        if self.reason is not None:
            record["reason"] = self.reason
        return record


def _normalize_expression_string(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return expr
    if expr.startswith("$"):
        body = expr[1:].strip()
        if body.startswith("."):
            return f"$ctx{body}"
        return f"${body}"
    for prefix in _EXPRESSION_PREFIXES:
        if expr == prefix or expr.startswith(f"{prefix}."):
            return f"${expr}"
    return expr


def _is_expression_string(expr: str) -> bool:
    expr = expr.strip()
    if not expr:
        return False
    if _TEMPLATE_PATTERN.search(expr):
        return True
    return _normalize_expression_string(expr).startswith("$")
def _alias_from_expression(expr: str, index: int) -> str:
    normalized = _normalize_expression_string(expr)
    if normalized.startswith("$"):
        normalized = normalized[1:]
    parts = [p for p in normalized.split(".") if p]
    if not parts:
        return f"value_{index}"
    candidate = parts[-1]
    if candidate in _EXPRESSION_PREFIXES:
        return f"value_{index}"
    return candidate


class FlowError(Exception):
    """Raised when the flow configuration or runtime execution encounters an error."""


def _ensure_context(context: Optional[MutableMapping[str, Any]]) -> MutableMapping[str, Any]:
    if context is None:
        context = {}
    context.setdefault("steps", [])
    context.setdefault("joins", {})
    context.setdefault("errors", [])
    context.setdefault("payloads", {})
    context.setdefault("routing", {})
    return context


def _get_from_path(mapping: MutableMapping[str, Any], path: Optional[str]) -> Any:
    if not path:
        return None
    parts = [p for p in path.split(".") if p]
    current: Any = mapping
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _set_to_path(mapping: MutableMapping[str, Any], path: Optional[str], value: Any) -> None:
    if not path:
        return
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    current: MutableMapping[str, Any] = mapping
    for part in parts[:-1]:
        next_item = current.get(part)
        if not isinstance(next_item, MutableMapping):
            next_item = {}
            current[part] = next_item
        current = next_item
    current[parts[-1]] = value


def _import_object(path: str) -> Any:
    module_path, _, attr = path.rpartition(".")
    if not module_path:
        raise FlowError(f"Invalid import path '{path}'")
    module = import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise FlowError(f"Unable to import '{path}'") from exc


def _load_config_source(source: Union[str, Path, Mapping[str, Any]]) -> Dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)

    if isinstance(source, (str, Path)):
        path = Path(source)
        text = path.read_text()
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise FlowError("PyYAML is required to load YAML configurations") from exc
            data = yaml.safe_load(text) or {}
        elif suffix == ".json":
            data = json.loads(text)
        else:
            raise FlowError(f"Unsupported config format '{suffix}'")
        return data

    raise FlowError("Config source must be a mapping or path to YAML/JSON file")


def _alias_from_path(path: str) -> str:
    parts = [p for p in path.split(".") if p]
    return parts[-1] if parts else path


def _normalize_inputs_spec(value: Optional[Any]) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    if value is None:
        return result

    def add(expr: str, alias: Optional[str] = None) -> None:
        expr = _normalize_expression_string(expr)
        normalized_alias = alias or _alias_from_expression(expr, len(result))
        result.append((normalized_alias, expr))

    if isinstance(value, str):
        add(value)
    elif isinstance(value, Mapping):
        for alias, expr in value.items():
            add(expr, alias)
    elif isinstance(value, Iterable):
        for item in value:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, Mapping):
                for alias, expr in item.items():
                    add(expr, alias)
            else:
                raise FlowError("Unsupported inputs specification item")
    else:
        raise FlowError("Inputs specification must be a string, mapping, or iterable")

    return result


def _normalize_outputs_spec(value: Optional[Any]) -> List[Tuple[Optional[str], str, bool]]:
    result: List[Tuple[Optional[str], str, bool]] = []
    if value is None:
        return result

    def add(expr: str, alias: Optional[str] = None, explicit: bool = False) -> None:
        expr = expr.strip()
        if not expr:
            return
        normalized = _normalize_output_target(expr)
        normalized_alias: Optional[str] = alias if explicit else None
        if explicit and not normalized_alias:
            normalized_alias = _alias_from_path(normalized)
        result.append((normalized_alias, normalized, explicit))

    if isinstance(value, str):
        add(value)
    elif isinstance(value, Mapping):
        for alias, expr in value.items():
            add(expr, alias, True)
    elif isinstance(value, Iterable):
        for item in value:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, Mapping):
                for alias, expr in item.items():
                    add(expr, alias, True)
            else:
                raise FlowError("Unsupported outputs specification item")
    else:
        raise FlowError("Outputs specification must be a string, mapping, or iterable")

    return result


def _normalize_output_target(expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("$"):
        expr = expr[1:]
        if expr.startswith("."):
            expr = f"ctx{expr}"
    if not expr:
        raise FlowError("Output target cannot be empty")
    for scope in ("ctx", "payload", "joins"):
        if expr.startswith(f"{scope}."):
            return expr
    raise FlowError("Output target must start with 'ctx.', 'payload.', or 'joins.'")


def _parse_target_expression(expr: str) -> Tuple[str, str]:
    expr = expr.strip()
    if expr.startswith("$"):
        expr = expr[1:]
        if expr.startswith("."):
            expr = f"ctx{expr}"
    parts = [p for p in expr.split(".") if p]
    if len(parts) < 2:
        raise FlowError("Output target must include scope and path (e.g. 'ctx.data.value')")
    scope = parts[0]
    if scope not in ("ctx", "payload", "joins"):
        raise FlowError(f"Unsupported output scope '{scope}'")
    relative = ".".join(parts[1:])
    if not relative:
        raise FlowError("Output target must include at least one key after the scope")
    return scope, relative


def _resolve_scope_mapping(context: MutableMapping[str, Any], scope: str) -> MutableMapping[str, Any]:
    if scope == "ctx":
        return context
    if scope == "payload":
        return context.setdefault("payloads", {})
    if scope == "joins":
        return context.setdefault("joins", {})
    raise FlowError(f"Unsupported scope '{scope}'")


def _resolve_reference(context: MutableMapping[str, Any], reference: str) -> Any:
    reference = _normalize_expression_string(reference)
    if not reference.startswith("$"):
        return reference
    reference = reference[1:]
    parts = [p for p in reference.split(".") if p]
    if not parts:
        return None
    scope = parts[0]
    if scope == "ctx":
        base: Any = context
    elif scope == "payload":
        base = context.get("payloads", {})
    elif scope == "joins":
        base = context.get("joins", {})
    elif scope == "env":
        key = ".".join(parts[1:])
        return os.environ.get(key, "")
    else:
        raise FlowError(f"Unknown expression scope '{scope}'")

    if len(parts) == 1:
        return base
    target = _get_from_path(base, ".".join(parts[1:])) if isinstance(base, MutableMapping) else None
    return target


def _evaluate_expression(context: MutableMapping[str, Any], expr: Any) -> Any:
    if expr is None or not isinstance(expr, str):
        return expr
    expr = expr.strip()
    if not expr:
        return expr

    if _TEMPLATE_PATTERN.search(expr):
        def replace(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            inner = _normalize_expression_string(inner)
            value = _evaluate_expression(context, inner)
            return "" if value is None else str(value)

        return _TEMPLATE_PATTERN.sub(replace, expr)

    expr = _normalize_expression_string(expr)
    if expr.startswith("$"):
        return _resolve_reference(context, expr)
    return expr


class Node:
    """Base node interface. Subclasses must implement :meth:`run`."""

    def __init__(
        self,
        *,
        name: str,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        allow_context_access: bool = False,
    ) -> None:
        if not name:
            raise FlowError("Node 'name' must be a non-empty string")
        self.name = name
        self._inputs: List[Tuple[str, str]] = _normalize_inputs_spec(inputs)
        self._outputs: List[Tuple[Optional[str], str, bool]] = _normalize_outputs_spec(outputs)
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._node_id: Optional[str] = None
        self._allow_context_access = allow_context_access
        self._active_context: Optional[MutableMapping[str, Any]] = None

    # --- Lifecycle helpers -------------------------------------------------

    def bind(self, node_id: str) -> None:
        """Bind the runtime-assigned node identifier."""

        self._node_id = node_id
        if not self.name:
            self.name = node_id

    @property
    def node_id(self) -> str:
        if self._node_id is None:
            raise FlowError("Node is not bound to a flow yet")
        return self._node_id

    def run(self, payload: Any) -> Any:
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        base = {
            "name": self.name or self._node_id,
            "module": self.__class__.__module__,
            "class": self.__class__.__name__,
            "inputs": [{"alias": alias, "path": path} for alias, path in self._inputs],
            "outputs": [
                {"alias": alias or _alias_from_path(path), "path": path}
                for alias, path, _ in self._outputs
            ],
            "allow_context_access": self._allow_context_access,
        }
        base.update(self._metadata)
        return base

    # --- Utilities ----------------------------------------------------------

    def _execute(self, payload: Any, context: MutableMapping[str, Any]) -> Any:
        if self._node_id is None:
            raise FlowError("Node must be bound before execution")
        previous_context = self._active_context
        self._active_context = context
        try:
            return self.run(payload)
        finally:
            self._active_context = previous_context

    def _set_output(self, context: MutableMapping[str, Any], value: Any) -> None:
        if self._node_id is None:
            raise FlowError("Node output cannot be recorded before binding to a flow")
        payloads = context.setdefault("payloads", {})
        payloads[self._node_id] = value
        if self._outputs:
            for alias, target_expr, explicit in self._outputs:
                scope, rel_path = _parse_target_expression(target_expr)
                target_mapping = _resolve_scope_mapping(context, scope)

                to_store = value
                if explicit and alias:
                    if isinstance(value, Mapping) and alias in value:
                        to_store = value[alias]
                    else:
                        to_store = value
                elif alias and isinstance(value, Mapping) and alias in value:
                    to_store = value[alias]

                _set_to_path(target_mapping, rel_path, to_store)

    def request_context(self) -> MutableMapping[str, Any]:
        if not self._allow_context_access:
            raise FlowError(
                "Context access is disabled for this node. Enable 'allow_context_access' if required."
            )
        if self._active_context is None:
            raise FlowError("Context is only available during active node execution")
        return self._active_context


class RoutingNode(Node):
    """Node variant that must return :class:`Routing` decisions."""

    def run(self, payload: Any) -> Union[Routing, Sequence[Routing]]:  # type: ignore[override]
        raise NotImplementedError

    def _ensure_routing(self, value: Any) -> List[Tuple[Routing, Any]]:
        def convert(item: Any) -> Tuple[Routing, Any]:
            if isinstance(item, Routing):
                return (item, None)
            if (
                isinstance(item, Sequence)
                and not isinstance(item, (str, bytes))
                and len(item) == 2
                and isinstance(item[0], Routing)
            ):
                return (item[0], item[1])
            raise FlowError(
                "RoutingNode must return Routing instances or (Routing, payload) tuples"
            )

        if isinstance(value, Routing):
            return [convert(value)]
        if (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
            and value
        ):
            results: List[Tuple[Routing, Any]] = []
            for item in value:
                results.append(convert(item))
            return results
        if value in (None, []):
            return []
        return [convert(value)]


class FunctionNode(Node):
    """Node that wraps a callable of signature ``callable(payload, context)``."""

    def __init__(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        callable_expression: Optional[str] = None,
        name: str,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        allow_context_access: bool = False,
    ) -> None:
        if func is None and callable_expression is None:
            raise FlowError("FunctionNode requires either 'func' or 'callable_expression'")

        super().__init__(
            name=name,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            allow_context_access=allow_context_access,
        )
        self._func: Optional[Callable[..., Any]] = func
        self._callable_expression = callable_expression

    def _resolve_callable(self, context: MutableMapping[str, Any], value: Any) -> Callable[..., Any]:
        if callable(value):
            return value
        if isinstance(value, str):
            target = value.strip()
            if not target:
                raise FlowError("Callable string cannot be empty")
            try:
                return _import_object(target)
            except FlowError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise FlowError(f"Unable to import callable '{target}'") from exc
        raise FlowError("Callable value must be a function or import path string")

    def _effective_callable(
        self,
        context: MutableMapping[str, Any],
        payload: Any,
    ) -> Tuple[Callable[..., Any], Any]:
        dynamic_value: Optional[Any] = None
        current_payload = payload

        if self._callable_expression is not None:
            dynamic_value = _evaluate_expression(context, self._callable_expression)

        if isinstance(payload, Mapping) and "callable" in payload:
            dynamic_value = payload["callable"]
            remaining = {k: v for k, v in payload.items() if k != "callable"}
            if len(remaining) == 0:
                current_payload = None
            elif len(remaining) == 1:
                current_payload = next(iter(remaining.values()))
            else:
                current_payload = remaining

        effective = self._func
        if dynamic_value is not None:
            effective = self._resolve_callable(context, dynamic_value)

        if effective is None:
            raise FlowError("FunctionNode has no callable to execute")

        return effective, current_payload

    def _invoke_callable(
        self,
        func: Callable[..., Any],
        payload: Any,
        context: Optional[MutableMapping[str, Any]],
    ) -> Any:
        import inspect

        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):  # pragma: no cover - defensive for builtins
            signature = None

        context_names = {"context", "ctx"}
        payload_names = {"payload", "value", "data", "input", "item", "items"}
        can_supply_context = context is not None

        if signature is not None:
            positional = [
                param
                for param in signature.parameters.values()
                if param.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]

            if not positional:
                return func()

            if len(positional) == 1:
                first = positional[0]
                if first.name in context_names:
                    if not can_supply_context:
                        raise FlowError(
                            "Callable expects context but 'allow_context_access' is disabled for this node"
                        )
                    return func(context)
                return func(payload)

            first, second = positional[0], positional[1]

            if first.name in context_names and second.name in payload_names:
                if not can_supply_context:
                    raise FlowError(
                        "Callable expects context but 'allow_context_access' is disabled for this node"
                    )
                return func(context, payload)

            if first.name in payload_names and second.name in context_names:
                if not can_supply_context:
                    raise FlowError(
                        "Callable expects context but 'allow_context_access' is disabled for this node"
                    )
                return func(payload, context)

            if first.name in payload_names:
                return func(payload)

            if first.name in context_names:
                if not can_supply_context:
                    raise FlowError(
                        "Callable expects context but 'allow_context_access' is disabled for this node"
                    )
                if len(positional) == 2 and second.name not in context_names:
                    return func(context, payload)
                return func(context)

            if can_supply_context:
                try:
                    return func(payload, context)
                except TypeError:
                    return func(context, payload)

            return func(payload)

        # Fallback when signature inspection is unavailable
        if can_supply_context:
            try:
                return func(payload, context)
            except TypeError:
                return func(context, payload)
        return func(payload)

    def run(self, payload: Any) -> Any:
        context = self._active_context
        if context is None:
            raise FlowError("FunctionNode cannot execute without an active flow context")
        func, effective_payload = self._effective_callable(context, payload)
        context_for_callable = context if self._allow_context_access else None
        result = self._invoke_callable(func, effective_payload, context_for_callable)
        if isinstance(result, tuple) and len(result) == 2:
            output, delta = result
            if isinstance(delta, Mapping):
                if context_for_callable is None:
                    raise FlowError(
                        "Callable attempted to mutate context without enabling 'allow_context_access'"
                    )
                context_for_callable.update(delta)
            return output
        return result


class CustomRoutingNode(RoutingNode):
    """Routing node powered by a user supplied callable returning :class:`Routing`."""

    def __init__(
        self,
        routing_rule: Optional[Callable[..., Any]] = None,
        *,
        routing_rule_expression: Optional[str] = None,
        name: str,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        allow_context_access: bool = False,
    ) -> None:
        if routing_rule is None and routing_rule_expression is None:
            raise FlowError(
                "CustomRoutingNode requires 'routing_rule' or 'routing_rule_expression'"
            )

        super().__init__(
            name=name,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            allow_context_access=allow_context_access,
        )
        self._routing_rule = routing_rule
        self._routing_rule_expression = routing_rule_expression

    def _resolve_routing_rule(self, value: Any) -> Callable[..., Any]:
        if callable(value):
            return value
        if isinstance(value, str):
            target = value.strip()
            if not target:
                raise FlowError("Routing rule string cannot be empty")
            try:
                return _import_object(target)
            except FlowError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise FlowError(f"Unable to import routing rule '{target}'") from exc
        raise FlowError("Routing rule must be a callable or import path string")

    def _effective_routing_rule(
        self,
        context: MutableMapping[str, Any],
        payload: Any,
    ) -> Tuple[Callable[..., Any], Any]:
        dynamic_value: Optional[Any] = None
        current_payload = payload

        if self._routing_rule_expression is not None:
            dynamic_value = _evaluate_expression(context, self._routing_rule_expression)

        if isinstance(payload, Mapping) and "routing_rule" in payload:
            dynamic_value = payload["routing_rule"]
            remaining = {k: v for k, v in payload.items() if k != "routing_rule"}
            if len(remaining) == 0:
                current_payload = None
            elif len(remaining) == 1:
                current_payload = next(iter(remaining.values()))
            else:
                current_payload = remaining

        if dynamic_value is not None:
            routing_callable = self._resolve_routing_rule(dynamic_value)
        elif self._routing_rule is not None:
            routing_callable = self._resolve_routing_rule(self._routing_rule)
        else:
            raise FlowError("CustomRoutingNode has no routing rule configured")

        return routing_callable, current_payload

    @staticmethod
    def _invoke_routing_rule(
        routing_callable: Callable[..., Any],
        payload: Any,
        context: Optional[MutableMapping[str, Any]],
    ) -> Any:
        import inspect

        try:
            signature = inspect.signature(routing_callable)
            parameters = list(signature.parameters.values())
        except (TypeError, ValueError):
            parameters = []

        can_supply_context = context is not None
        expects_payload = True

        if parameters:
            first_param = parameters[0]
            if first_param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                expects_payload = True
            else:
                expects_payload = payload is not None or first_param.default is inspect._empty
        else:
            expects_payload = False

        if can_supply_context:
            if expects_payload:
                try:
                    return routing_callable(payload, context)
                except TypeError:
                    return routing_callable(context, payload)
            try:
                return routing_callable(context)
            except TypeError:
                return routing_callable()

        if expects_payload:
            try:
                return routing_callable(payload)
            except TypeError:
                return routing_callable()

        return routing_callable()

    def run(self, payload: Any) -> Routing:  # type: ignore[override]
        context = self._active_context
        if context is None:
            raise FlowError("CustomRoutingNode cannot execute without an active flow context")

        routing_callable, effective_payload = self._effective_routing_rule(context, payload)
        context_for_callable = context if self._allow_context_access else None
        result = self._invoke_routing_rule(routing_callable, effective_payload, context_for_callable)

        if isinstance(result, tuple) and len(result) == 2:
            output, delta = result
            if isinstance(delta, Mapping):
                if context_for_callable is None:
                    raise FlowError(
                        "Routing rule attempted to mutate context without enabling 'allow_context_access'"
                    )
                context_for_callable.update(delta)
            result = output

        return self._ensure_routing(result)


class LoopNode(RoutingNode):
    """Iterate over a sequence payload and emit items to a downstream node."""

    _STATE_KEY = "__loop_state__"

    def __init__(
        self,
        *,
        name: str,
        body_route: str,
        loop_route: Optional[str] = None,
        items_key: Optional[str] = None,
        enumerate_items: bool = False,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not body_route:
            raise FlowError("LoopNode requires 'body_route' to identify the iteration target")
        super().__init__(
            name=name,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
        )
        self._body_route = body_route
        self._loop_route = loop_route
        self._items_key = items_key
        self._enumerate = enumerate_items

    def run(self, payload: Any) -> Any:
        state = self._state_from_payload(payload)
        items = state["items"]
        index = state["index"]

        print(f"[LoopNode] enter node={self.name} state index={index} len={len(items)}", flush=True)
        if index >= len(items):
            print(f"[LoopNode] node={self.name} complete len={len(items)}", flush=True)
            return []

        value = items[index]
        downstream_payload: Any
        if self._enumerate:
            downstream_payload = {"item": value, "index": index}
        else:
            downstream_payload = value

        routes: List[Tuple[Routing, Any]] = [(Routing(target=self._body_route), downstream_payload)]
        print(
            f"[LoopNode] node={self.name} index={index} len={len(items)} "
            f"emit={[route.target for route, _ in routes]}",
            flush=True,
        )

        next_index = index + 1
        if next_index < len(items):
            loop_target = self._loop_route or self.node_id
            result_payload = {
                self._STATE_KEY: {
                    "items": items,
                    "index": next_index,
                }
            }
            routes.append((Routing(target=loop_target), result_payload))
            print(
                f"[LoopNode] node={self.name} schedule next index={next_index} "
                f"target={loop_target}",
                flush=True,
            )
        return routes

    def _state_from_payload(self, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, Mapping):
            state_container: Optional[Mapping[str, Any]] = None
            if self._STATE_KEY in payload:
                state_container = payload
            elif self.node_id in payload and isinstance(payload[self.node_id], Mapping):
                node_payload = payload[self.node_id]
                if self._STATE_KEY in node_payload:
                    state_container = node_payload

            if state_container is not None:
                raw_state = state_container[self._STATE_KEY]
                try:
                    items = list(raw_state["items"])
                    index = int(raw_state.get("index", 0))
                except Exception as exc:  # pragma: no cover - defensive
                    raise FlowError("Invalid loop state payload") from exc
                self._validate_sequence(items)
                if index < 0 or index > len(items):
                    raise FlowError("Loop state index is out of range")
                return {"items": items, "index": index}

            if self._items_key is not None:
                sequence_source = payload.get(self._items_key)
            else:
                sequence_source = payload
        else:
            sequence_source = payload

        if sequence_source is None:
            items_list: List[Any] = []
        elif isinstance(sequence_source, Mapping):
            raise FlowError("LoopNode payload must be a sequence, not a mapping")
        elif isinstance(sequence_source, (str, bytes)):
            raise FlowError("LoopNode does not iterate over plain strings; provide a list instead")
        elif isinstance(sequence_source, Iterable):
            items_list = list(sequence_source)
        else:
            raise FlowError("LoopNode payload must be iterable")

        self._validate_sequence(items_list)
        return {"items": items_list, "index": 0}

    @staticmethod
    def _validate_sequence(items: Sequence[Any]) -> None:
        if not isinstance(items, Sequence):
            raise FlowError("LoopNode requires a concrete sequence to iterate")
class Flow:
    """Workflow runner that orchestrates bound nodes and edges."""

    def __init__(
        self,
        *,
        nodes: Mapping[str, Node],
        entry: Union[str, Node],
        edges: Iterable[Tuple[str, str]],
    ) -> None:
        if isinstance(entry, Node):
            raise FlowError("Entry must be specified by node identifier, not Node instance")

        if entry not in nodes:
            raise FlowError(f"Entry node '{entry}' not found in nodes mapping")

        self.nodes: Dict[str, Node] = {}
        for node_id, node in nodes.items():
            node.bind(node_id)
            self.nodes[node_id] = node

        self.entry_id = entry
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse: Dict[str, Set[str]] = defaultdict(set)

        for src, dst in edges:
            if src not in self.nodes:
                raise FlowError(f"Edge references unknown source node '{src}'")
            if dst not in self.nodes:
                raise FlowError(f"Edge references unknown target node '{dst}'")
            self.adjacency[src].add(dst)
            if src == dst:
                # Avoid counting self-loops as dependencies to keep entry nodes runnable/自己ループを依存関係に含めずエントリノードを実行可能に保つ
                continue
            self.reverse[dst].add(src)

        # Ensure every node appears in adjacency map
        for node_id in self.nodes:
            self.adjacency.setdefault(node_id, set())
            self.reverse.setdefault(node_id, set())

        self.parent_counts: Dict[str, int] = {
            node_id: len(parents) for node_id, parents in self.reverse.items()
        }
        self.parent_order: Dict[str, Tuple[str, ...]] = {
            node_id: tuple(sorted(parents)) for node_id, parents in self.reverse.items()
        }

        self.dependency_counts: Dict[str, int] = dict(self.parent_counts)

    # ------------------------------------------------------------------
    @classmethod
    def from_dsl(
        cls,
        *,
        nodes: Mapping[str, Node],
        entry: Union[str, Node],
        edges: Iterable[Union[str, Tuple[str, str]]],
    ) -> "Flow":
        expanded: List[Tuple[str, str]] = []
        for edge in edges:
            if isinstance(edge, tuple):
                expanded.append(edge)
            else:
                expanded.extend(cls._parse_edge_expression(edge))
        return cls(nodes=nodes, entry=entry, edges=expanded)

    # ------------------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        source: Union[str, Path, Mapping[str, Any]],
    ) -> "Flow":
        raw = _load_config_source(source)
        flow_cfg = raw.get("flow", raw)
        entry = flow_cfg.get("entry")
        if entry is None:
            raise FlowError("Config must define 'entry'")

        node_defs = flow_cfg.get("nodes", {})
        if not node_defs:
            raise FlowError("Config must define at least one node")

        nodes: Dict[str, Node] = {}
        for node_id, cfg in node_defs.items():
            node_type = cfg.get("type", "illumo_flow.core.FunctionNode")
            NodeCls = _import_object(node_type)

            context_cfg = dict(cfg.get("context", {}))
            inputs_cfg = context_cfg.get("inputs")
            outputs_cfg = context_cfg.get("outputs")
            if inputs_cfg is None and "input" in context_cfg:
                inputs_cfg = context_cfg.get("input")
            if outputs_cfg is None and "output" in context_cfg:
                outputs_cfg = context_cfg.get("output")

            callable_spec: Optional[Any] = None
            callable_expression: Optional[str] = None
            func_obj: Optional[Any] = None

            callable_keys = ("routing_rule", "callable")

            if isinstance(inputs_cfg, Mapping):
                inputs_cfg = dict(inputs_cfg)
                for candidate_key in callable_keys:
                    if candidate_key in inputs_cfg:
                        callable_spec = inputs_cfg.pop(candidate_key)
                        break
                context_cfg["inputs"] = inputs_cfg if inputs_cfg else None
            else:
                context_cfg["inputs"] = inputs_cfg

            if callable_spec is None:
                for candidate_key in callable_keys:
                    if candidate_key in cfg:
                        callable_spec = cfg.get(candidate_key)
                        break

            if callable_spec is not None:
                if isinstance(callable_spec, str) and not _is_expression_string(callable_spec):
                    func_obj = _import_object(callable_spec)
                elif isinstance(callable_spec, str):
                    callable_expression = callable_spec
                else:
                    raise FlowError("Callable specification must be a string")

            common_kwargs = {
                "name": cfg.get("name", node_id),
                "inputs": context_cfg.get("inputs"),
                "outputs": outputs_cfg,
                "metadata": cfg.get("describe"),
                "allow_context_access": cfg.get("allow_context_access"),
            }
            common_kwargs = {k: v for k, v in common_kwargs.items() if v is not None}

            if issubclass(NodeCls, FunctionNode):
                fn_kwargs = dict(common_kwargs)
                if func_obj is not None:
                    fn_kwargs["func"] = func_obj
                if callable_expression is not None:
                    fn_kwargs["callable_expression"] = callable_expression
                if "func" not in fn_kwargs and "callable_expression" not in fn_kwargs:
                    raise FlowError(
                        f"FunctionNode '{node_id}' requires a callable via 'context.inputs.callable' or 'callable'"
                    )
                try:
                    node = NodeCls(**fn_kwargs)
                except TypeError as exc:
                    raise FlowError(f"Unable to instantiate node '{node_id}': {exc}")
            elif issubclass(NodeCls, CustomRoutingNode):
                routing_kwargs = dict(common_kwargs)
                if func_obj is not None:
                    routing_kwargs["routing_rule"] = func_obj
                if callable_expression is not None:
                    routing_kwargs["routing_rule_expression"] = callable_expression
                if "routing_rule" not in routing_kwargs and "routing_rule_expression" not in routing_kwargs:
                    raise FlowError(
                        f"CustomRoutingNode '{node_id}' requires a rule via 'context.inputs.routing_rule' or 'routing_rule'"
                    )
                try:
                    node = NodeCls(**routing_kwargs)
                except TypeError as exc:
                    raise FlowError(f"Unable to instantiate node '{node_id}': {exc}")
            else:
                node = NodeCls(**common_kwargs)

            nodes[node_id] = node

        edges = flow_cfg.get("edges", [])
        return cls.from_dsl(nodes=nodes, entry=entry, edges=edges)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_edge_expression(expr: str) -> List[Tuple[str, str]]:
        text = expr.strip()
        if "<<" in text:
            raise FlowError(f"Invalid edge expression '{expr}'")
        if ">>" not in text:
            raise FlowError(f"Edge expression must contain '>>': '{expr}'")
        left, right = text.split(">>", 1)
        sources = Flow._split_terms(left)
        targets = Flow._split_terms(right)
        return [(src, dst) for src in sources for dst in targets]

    @staticmethod
    def _split_terms(segment: str) -> List[str]:
        segment = segment.strip()
        if segment.startswith("(") and segment.endswith(")"):
            segment = segment[1:-1]
        if not segment:
            raise FlowError("Empty segment in edge expression")
        terms = [term.strip() for term in segment.replace("&", "|").split("|")]
        return [t for t in terms if t]

    # ------------------------------------------------------------------
    def run(self, context: Optional[MutableMapping[str, Any]] = None, user_input: Any = None) -> Any:
        context = _ensure_context(context)
        payloads: MutableMapping[str, Any] = context.setdefault("payloads", {})
        payloads.setdefault(self.entry_id, user_input)

        ready = deque([self.entry_id])
        remaining = dict(self.dependency_counts)
        completed: Set[str] = set()
        in_queue: Set[str] = {self.entry_id}
        join_buffers: Dict[str, Dict[str, Any]] = defaultdict(dict)
        max_steps_env = os.environ.get("FLOW_DEBUG_MAX_STEPS")
        max_steps = int(max_steps_env) if max_steps_env else None
        step_counter = 0
        iteration = 0
        while ready:
            iteration += 1
            if iteration % 100 == 0:
                print(f"[Flow] iteration={iteration} queue={list(ready)}", flush=True)
            if max_steps is not None and step_counter >= max_steps:
                print(f"[Flow] debug break after {step_counter} steps", flush=True)
                break
            step_counter += 1
            node_id = ready.popleft()
            in_queue.discard(node_id)

            if node_id in completed:
                continue

            if remaining.get(node_id, 0) > 0:
                # Not ready yet; requeue and continue
                ready.append(node_id)
                in_queue.add(node_id)
                continue

            node = self.nodes[node_id]
            print(
                f"[Flow] executing node={node_id} ready={list(ready)} "
                f"remaining={remaining.get(node_id,0)}",
                flush=True,
            )
            context["steps"].append({"node_id": node_id, "status": "start"})

            input_payload = payloads.get(node_id)
            if getattr(node, "_inputs", None):
                resolved_inputs: Dict[str, Any] = {}
                for alias, expr in node._inputs:
                    resolved_inputs[alias] = _evaluate_expression(context, expr)
                if len(node._inputs) == 1:
                    input_payload = next(iter(resolved_inputs.values()))
                else:
                    input_payload = resolved_inputs
            try:
                raw_result = node._execute(input_payload, context)
            except Exception as exc:
                error_record = {
                    "node_id": node_id,
                    "exception": exc.__class__.__name__,
                    "message": str(exc),
                }
                context["errors"].append(error_record)
                context["failed_node_id"] = node_id
                context["failed_exception_type"] = exc.__class__.__name__
                context["failed_message"] = str(exc)
                context["steps"].append({"node_id": node_id, "status": "failed", "message": str(exc)})
                raise

            routing_entries: Optional[List[Tuple[Routing, Any]]] = None
            branch_payloads: Optional[Dict[str, Any]] = None
            if isinstance(node, RoutingNode):
                routing_entries = node._ensure_routing(raw_result)
                branch_payloads = {}
                recorded_payloads: List[Any] = []
                for route, override in routing_entries:
                    payload_for_route = override
                    if payload_for_route is None:
                        payload_for_route = input_payload
                    branch_payloads[route.target] = payload_for_route
                    recorded_payloads.append(payload_for_route)
                result_to_store = branch_payloads
            else:
                if isinstance(raw_result, Routing):
                    raise FlowError(
                        f"Node '{node_id}' returned a Routing result but is not a RoutingNode"
                    )
                result_to_store = raw_result

            if result_to_store is None and input_payload is not None:
                result_to_store = input_payload

            node._set_output(context, result_to_store)

            if routing_entries is not None:
                context["routing"][node_id] = [route.to_context() for route, _ in routing_entries]

            context["payloads"][node_id] = result_to_store
            context["steps"].append({"node_id": node_id, "status": "success"})
            completed.add(node_id)
            requeue_self = False

            branch_keys: Optional[Set[str]] = None
            if routing_entries is not None:
                branch_keys = {route.target for route, _ in routing_entries}
                if not branch_keys:
                    print(
                        f"[Flow] node={node_id} produced empty routing -> stopping successors",
                        flush=True,
                    )
                    continue

            successors = self._resolve_successors(node, context, branch_keys=branch_keys)
            if not successors:
                continue

            branch_payload_map = branch_payloads or {}
            if routing_entries is not None:
                ordered_entries = [entry for entry in routing_entries if entry[0].target in successors]
                route_iterable: Iterable[Tuple[str, Any]] = (
                    (route.target, branch_payload_map.get(route.target))
                    for route, _ in ordered_entries
                )
            else:
                route_iterable = ((target, result_to_store) for target in successors)

            for target, payload_candidate in route_iterable:
                print(f"[Flow] enqueue candidate target={target} from node={node_id}", flush=True)
                if routing_entries is not None and target not in successors:
                    print(
                        f"[Flow] skip target={target} not in routing successors",
                        flush=True,
                    )
                    continue

                next_payload = payload_candidate
                if next_payload is None:
                    next_payload = input_payload

                remaining[target] = remaining.get(target, self.parent_counts[target])
                remaining[target] = max(0, remaining[target] - 1)

                parent_count = self.parent_counts.get(target, 0)
                if parent_count > 1:
                    joins_map = context.setdefault("joins", {})
                    join_entry = joins_map.setdefault(target, {})
                    join_entry[node_id] = next_payload
                    join_buffers[target][node_id] = next_payload
                    if len(join_buffers[target]) == parent_count:
                        ordered_parents = self.parent_order.get(target, tuple(join_buffers[target].keys()))
                        aggregated = {
                            parent: join_buffers[target][parent]
                            for parent in ordered_parents
                            if parent in join_buffers[target]
                        }
                        context["payloads"][target] = aggregated
                        joins_map[target] = aggregated
                        join_buffers[target].clear()
                else:
                    context["payloads"][target] = next_payload

                if target in completed:
                    completed.discard(target)  # Allow re-execution when new payload arrives/新しいペイロードで再実行できるよう完了状態を解除

                if remaining[target] == 0 and target not in completed and target not in in_queue:
                    print(f"[Flow] append target={target} to ready queue", flush=True)
                    ready.append(target)
                    in_queue.add(target)

                if target == node_id and (branch_keys is None or node_id not in branch_keys):
                    requeue_self = True

            if requeue_self:
                completed.discard(node_id)
                ready.append(node_id)
                in_queue.add(node_id)

            print(
                f"[Flow] end iteration ready={list(ready)} completed={completed}",
                flush=True,
            )

        return context

    # ------------------------------------------------------------------
    def _resolve_successors(
        self,
        node: Node,
        context: MutableMapping[str, Any],
        *,
        branch_keys: Optional[Set[str]] = None,
    ) -> Optional[Set[str]]:
        allowed = self.adjacency.get(node.node_id, set())
        if not allowed:
            return set()

        if branch_keys is not None:
            invalid = branch_keys - allowed
            if invalid:
                raise FlowError(
                    f"Node '{node.node_id}' returned unknown successors: {sorted(invalid)}"
                )
            return branch_keys

        return set(allowed)
