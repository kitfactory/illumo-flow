"""Core Flow orchestration primitives."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_EXPRESSION_PREFIXES = ("ctx", "payload", "joins", "env")


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


class ContextView:
    """Limited context access exposed to nodes during execution."""

    __slots__ = ("_context", "_node_id")

    def __init__(self, context: MutableMapping[str, Any], node_id: str) -> None:
        self._context = context
        self._node_id = node_id

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def raw(self) -> MutableMapping[str, Any]:
        """Direct access to the underlying context (use sparingly)."""

        return self._context

    def get(self, expression: str, default: Any = None) -> Any:
        value = _evaluate_expression(self._context, expression)
        return default if value is None else value

    def write(self, target: str, value: Any) -> None:
        normalized = _normalize_output_target(target)
        scope, rel_path = _parse_target_expression(normalized)
        mapping = _resolve_scope_mapping(self._context, scope)
        _set_to_path(mapping, rel_path, value)

    def route(
        self,
        *,
        next: Optional[Union[str, Sequence[str]]] = None,
        confidence: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        self._context["routing"][self._node_id] = Routing(next=next, confidence=confidence, reason=reason)


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


@dataclass(slots=True)
class Routing:
    """Routing decision emitted by a node and stored in context."""

    next: Optional[Union[str, Sequence[str]]] = None
    confidence: Optional[int] = None
    reason: Optional[str] = None


def _ensure_context(context: Optional[MutableMapping[str, Any]]) -> MutableMapping[str, Any]:
    if context is None:
        context = {}
    context.setdefault("steps", [])
    context.setdefault("routing", {})
    context.setdefault("joins", {})
    context.setdefault("errors", [])
    context.setdefault("payloads", {})
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
        next_route: Optional[str] = None,
        default_route: Optional[str] = None,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not name:
            raise FlowError("Node 'name' must be a non-empty string")
        self.name = name
        self.next_route = next_route
        self.default_route = default_route
        self._inputs: List[Tuple[str, str]] = _normalize_inputs_spec(inputs)
        self._outputs: List[Tuple[Optional[str], str, bool]] = _normalize_outputs_spec(outputs)
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._node_id: Optional[str] = None

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

    # --- Contracts ----------------------------------------------------------

    def run(self, payload: Any, *, context: MutableMapping[str, Any]) -> Any:
        if self._node_id is None:
            raise FlowError("Node must be bound before execution")
        ctx_view = ContextView(context, self._node_id)
        result = self.handle(payload, ctx_view)
        if result is None and payload is not None:
            result_to_store = payload
        else:
            result_to_store = result
        self._set_output(context, result_to_store)
        return result_to_store

    async def run_async(self, payload: Any, *, context: MutableMapping[str, Any]) -> Any:
        return self.run(payload, context=context)

    def handle(self, payload: Any, ctx: ContextView) -> Any:
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        base = {
            "name": self.name or self._node_id,
            "module": self.__class__.__module__,
            "class": self.__class__.__name__,
            "next_route": self.next_route,
            "default_route": self.default_route,
            "inputs": [{"alias": alias, "path": path} for alias, path in self._inputs],
            "outputs": [
                {"alias": alias or _alias_from_path(path), "path": path}
                for alias, path, _ in self._outputs
            ],
        }
        base.update(self._metadata)
        return base

    # --- Utilities ----------------------------------------------------------

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


class FunctionNode(Node):
    """Node that wraps a callable of signature ``callable(payload, ctx_view)``."""

    def __init__(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        callable_expression: Optional[str] = None,
        name: str,
        next_route: Optional[str] = None,
        default_route: Optional[str] = None,
        inputs: Optional[Any] = None,
        outputs: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if func is None and callable_expression is None:
            raise FlowError("FunctionNode requires either 'func' or 'callable_expression'")

        super().__init__(
            name=name,
            next_route=next_route,
            default_route=default_route,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
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

    def _effective_callable(self, context: MutableMapping[str, Any], user_input: Any) -> Tuple[Callable[..., Any], Any]:
        dynamic_value: Optional[Any] = None
        payload = user_input

        if self._callable_expression is not None:
            dynamic_value = _evaluate_expression(context, self._callable_expression)

        if isinstance(user_input, Mapping) and "callable" in user_input:
            dynamic_value = user_input["callable"]
            remaining = {k: v for k, v in user_input.items() if k != "callable"}
            if len(remaining) == 0:
                payload = None
            elif len(remaining) == 1:
                payload = next(iter(remaining.values()))
            else:
                payload = remaining

        effective = self._func
        if dynamic_value is not None:
            effective = self._resolve_callable(context, dynamic_value)

        if effective is None:
            raise FlowError("FunctionNode has no callable to execute")

        return effective, payload

    def _invoke_callable(self, func: Callable[..., Any], payload: Any, ctx: ContextView) -> Any:
        import inspect

        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):  # pragma: no cover - builtins or C callables
            signature = None

        if signature is not None:
            params = list(signature.parameters.values())
            if len(params) == 1:
                return func(payload)
            if len(params) == 2:
                first, second = params
                if first.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) and second.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                    if first.name in {"payload", "value", "data", "input"}:
                        return func(payload, ctx)
                    if second.name in {"payload", "value", "data", "input"}:
                        return func(ctx.raw, payload)
        try:
            return func(payload, ctx)
        except TypeError:
            try:
                return func(payload)
            except TypeError:
                return func(ctx.raw, payload)

    def handle(self, payload: Any, ctx: ContextView) -> Any:
        func, effective_payload = self._effective_callable(ctx.raw, payload)
        result = self._invoke_callable(func, effective_payload, ctx)
        if isinstance(result, tuple) and len(result) == 2:
            output, delta = result
            if isinstance(delta, Mapping):
                ctx.raw.update(delta)
            return output
        return result


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

            if isinstance(inputs_cfg, Mapping) and "callable" in inputs_cfg:
                inputs_cfg = dict(inputs_cfg)
                callable_spec = inputs_cfg.pop("callable")
                context_cfg["inputs"] = inputs_cfg if inputs_cfg else None
            else:
                context_cfg["inputs"] = inputs_cfg

            if callable_spec is None:
                callable_spec = cfg.get("callable")

            if callable_spec is not None:
                if isinstance(callable_spec, str) and not _is_expression_string(callable_spec):
                    func_obj = _import_object(callable_spec)
                elif isinstance(callable_spec, str):
                    callable_expression = callable_spec
                else:
                    raise FlowError("Callable specification must be a string")

            common_kwargs = {
                "name": cfg.get("name", node_id),
                "next_route": cfg.get("next_route"),
                "default_route": cfg.get("default_route"),
                "inputs": context_cfg.get("inputs"),
                "outputs": outputs_cfg,
                "metadata": cfg.get("describe"),
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
        while ready:
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
                result = node.run(input_payload, context=context)
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

            output_value = result
            context["payloads"][node_id] = output_value
            context["steps"].append({"node_id": node_id, "status": "success"})
            completed.add(node_id)

            successors = self._resolve_successors(node, context)
            if not successors:
                continue

            for target in successors:
                remaining[target] = remaining.get(target, self.parent_counts[target])
                remaining[target] = max(0, remaining[target] - 1)

                parent_count = self.parent_counts.get(target, 0)
                if parent_count > 1:
                    joins_map = context.setdefault("joins", {})
                    join_entry = joins_map.setdefault(target, {})
                    join_entry[node_id] = output_value
                    join_buffers[target][node_id] = output_value
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
                    context["payloads"][target] = output_value

                if remaining[target] == 0 and target not in completed and target not in in_queue:
                    ready.append(target)
                    in_queue.add(target)

        return context

    # ------------------------------------------------------------------
    def _resolve_successors(self, node: Node, context: MutableMapping[str, Any]) -> Optional[Set[str]]:
        allowed = self.adjacency.get(node.node_id, set())
        if not allowed:
            return set()

        routing = context["routing"].pop(node.node_id, None)
        selected: Optional[Set[str]] = None

        if node.next_route:
            selected = {node.next_route}
        elif routing is not None:
            if isinstance(routing, Routing):
                raw_next = routing.next
            elif isinstance(routing, Mapping):
                raw_next = routing.get("next")
            else:
                raw_next = routing

            if raw_next is None:
                return None
            if isinstance(raw_next, str):
                selected = {raw_next}
            else:
                selected = set(raw_next)
        else:
            selected = set(allowed)

        if (not selected or len(selected) == 0) and node.default_route:
            selected = {node.default_route}

        if not selected:
            return set()

        invalid = selected - allowed
        if invalid:
            raise FlowError(f"Node '{node.node_id}' attempted to route to invalid successors: {sorted(invalid)}")

        # Ensure default route exists in graph
        return selected
