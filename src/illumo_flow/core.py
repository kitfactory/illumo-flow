"""Core Flow orchestration primitives."""

from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple, Union


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


class Node:
    """Base node interface. Subclasses must implement :meth:`run`."""

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        next_route: Optional[str] = None,
        default_route: Optional[str] = None,
        requires: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.next_route = next_route
        self.default_route = default_route
        self._requires: List[str] = []
        if requires:
            for node_id in requires:
                if node_id not in self._requires:
                    self._requires.append(node_id)
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._node_id: Optional[str] = None

    # --- Lifecycle helpers -------------------------------------------------

    def bind(self, node_id: str) -> None:
        """Bind the runtime-assigned node identifier."""

        self._node_id = node_id

    @property
    def node_id(self) -> str:
        if self._node_id is None:
            raise FlowError("Node is not bound to a flow yet")
        return self._node_id

    # --- Contracts ----------------------------------------------------------

    def requires_nodes(self, *node_ids: str) -> "Node":
        for node_id in node_ids:
            if node_id not in self._requires:
                self._requires.append(node_id)
        return self

    def requires(self, *node_ids: str) -> "Node":
        return self.requires_nodes(*node_ids)

    @property
    def required_parents(self) -> Tuple[str, ...]:
        return tuple(self._requires)

    def run(self, user_input: Any = None, context: Optional[MutableMapping[str, Any]] = None) -> MutableMapping[str, Any]:
        raise NotImplementedError

    async def run_async(self, user_input: Any = None, context: Optional[MutableMapping[str, Any]] = None) -> MutableMapping[str, Any]:
        return self.run(user_input, context)

    def describe(self) -> Dict[str, Any]:
        base = {
            "name": self.name,
            "module": self.__class__.__module__,
            "class": self.__class__.__name__,
            "requires": sorted(self._requires),
            "next_route": self.next_route,
            "default_route": self.default_route,
        }
        base.update(self._metadata)
        return base

    # --- Utilities ----------------------------------------------------------

    def _set_output(self, context: MutableMapping[str, Any], value: Any) -> None:
        if self._node_id is None:
            raise FlowError("Node output cannot be recorded before binding to a flow")
        payloads = context.setdefault("payloads", {})
        payloads[self._node_id] = value


class FunctionNode(Node):
    """Node that wraps a callable of signature ``callable(context, payload)``."""

    def __init__(
        self,
        func,
        *,
        name: Optional[str] = None,
        next_route: Optional[str] = None,
        default_route: Optional[str] = None,
        requires: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(
            name=name,
            next_route=next_route,
            default_route=default_route,
            requires=requires,
            metadata=metadata,
        )
        self._func = func

    def run(self, user_input: Any = None, context: Optional[MutableMapping[str, Any]] = None) -> MutableMapping[str, Any]:
        context = _ensure_context(context)
        result = self._func(context, user_input)
        output = result
        if isinstance(result, tuple) and len(result) == 2:
            output, delta = result
            if isinstance(delta, Mapping):
                context.update(delta)
        self._set_output(context, output)
        return context


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

        self.requires_map: Dict[str, Tuple[str, ...]] = {
            node_id: node.required_parents for node_id, node in self.nodes.items() if node.required_parents
        }

        # Validate requires are satisfied by edges
        for node_id, required in self.requires_map.items():
            missing = set(required) - self.reverse[node_id]
            if missing:
                raise FlowError(
                    f"Node '{node_id}' declares requires {sorted(required)} but edges missing parents {sorted(missing)}"
                )

        self.dependency_counts: Dict[str, int] = {
            node_id: len(parents) for node_id, parents in self.reverse.items()
        }

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
        last_output: Any = None

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
            try:
                updated_context = node.run(user_input=input_payload, context=context)
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

            if updated_context is not None:
                context = _ensure_context(updated_context)

            output_value = context["payloads"].get(node_id, input_payload)
            last_output = output_value
            context["steps"].append({"node_id": node_id, "status": "success"})
            completed.add(node_id)

            successors = self._resolve_successors(node, context)
            if not successors:
                continue

            for target in successors:
                remaining[target] = remaining.get(target, len(self.reverse[target]))
                remaining[target] = max(0, remaining[target] - 1)

                if target in self.requires_map:
                    join_buffers[target][node_id] = output_value
                    if len(join_buffers[target]) == len(self.requires_map[target]):
                        ordered = {key: join_buffers[target][key] for key in self.requires_map[target]}
                        context["payloads"][target] = ordered
                else:
                    context["payloads"][target] = output_value

                if remaining[target] == 0 and target not in completed and target not in in_queue:
                    ready.append(target)
                    in_queue.add(target)

        return last_output

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
