"""Workspace-oriented node implementations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, MutableMapping, Optional, Sequence

from ..core import FlowError, Node, NodeConfig, _parse_target_expression, _resolve_scope_mapping, _set_to_path


def _normalize_extensions(raw: Optional[Iterable[str]]) -> Sequence[str]:
    if not raw:
        return (".py", ".txt", ".md", ".json", ".yaml")
    normalized: List[str] = []
    for item in raw:
        ext = str(item).strip()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        normalized.append(ext.lower())
    return tuple(dict.fromkeys(normalized))  # preserve order, drop duplicates


def _is_within_path(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _read_text_preview(path: Path, *, head_lines: int, max_bytes: int) -> Optional[str]:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > max_bytes:
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if head_lines <= 0:
        return ""
    lines = content.splitlines()
    if len(lines) <= head_lines * 2:
        return "\n".join(lines[: head_lines * 2])
    head = lines[:head_lines]
    tail = lines[-head_lines:]
    return "\n".join(head + ["..."] + tail)


@dataclass
class WorkspaceEntry:
    path: str
    size: int
    preview: str
    selected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "preview": self.preview,
            "selected": self.selected,
        }


@dataclass
class ExcludedEntry:
    path: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "reason": self.reason}


class WorkspaceInspectorNode(Node):
    """Collect file metadata and previews from a workspace."""

    DEFAULT_PREVIEW_LINES = 20
    DEFAULT_MAX_BYTES = 128 * 1024

    def __init__(self, *, config: NodeConfig) -> None:
        super().__init__(config=config)
        self._default_root = config.setting_value("default_root") or "."

        allowed = config.setting_value("allowed_extensions")
        if isinstance(allowed, str):
            allowed_iterable = [part.strip() for part in allowed.split(",") if part.strip()]
        else:
            allowed_iterable = allowed
        self._allowed_extensions = _normalize_extensions(allowed_iterable)

        preview_lines = config.setting_value("preview_lines")
        if preview_lines is None:
            self._preview_lines = self.DEFAULT_PREVIEW_LINES
        else:
            self._preview_lines = int(preview_lines)
            if self._preview_lines < 0:
                raise FlowError("WorkspaceInspectorNode 'preview_lines' must be >= 0")

        max_bytes = config.setting_value("max_bytes")
        if max_bytes is None:
            self._max_bytes = self.DEFAULT_MAX_BYTES
        else:
            self._max_bytes = int(max_bytes)
            if self._max_bytes <= 0:
                raise FlowError("WorkspaceInspectorNode 'max_bytes' must be > 0")

        self._output_path = config.setting_value("output_path")
        self._excluded_path = config.setting_value("excluded_path")

    # ------------------------------------------------------------------
    def run(self, payload: Any) -> MutableMapping[str, Any]:  # type: ignore[override]
        context = self.request_context()
        request = context.setdefault("request", {})

        root_setting = request.get("target_root") or self._default_root
        root_path = Path(root_setting).expanduser()
        if not root_path.is_absolute():
            root_path = Path.cwd() / root_path
        root_path = root_path.resolve()
        if not root_path.exists():
            raise FlowError(f"Workspace root '{root_path}' does not exist")

        target_files = request.get("target_files") or []
        if isinstance(target_files, str):
            target_files = [target_files]
        selected_paths = {
            Path(str(item)).as_posix(): Path(str(item)) for item in target_files
        }
        selected_relatives: set[str] = set()

        structure: List[WorkspaceEntry] = []
        excluded: List[ExcludedEntry] = []

        def rel_path(path: Path) -> str:
            return path.resolve().relative_to(root_path).as_posix()

        candidates: List[Path] = []
        if selected_paths:
            for rel, rel_path_obj in selected_paths.items():
                candidate = (root_path / rel_path_obj).resolve()
                if not _is_within_path(root_path, candidate):
                    excluded.append(ExcludedEntry(path=str(rel_path_obj), reason="outside-root"))
                    continue
                selected_relatives.add(rel_path(candidate))
                candidates.append(candidate)
        else:
            for path in root_path.rglob("*"):
                if not _is_within_path(root_path, path):
                    excluded.append(ExcludedEntry(path=path.as_posix(), reason="outside-root"))
                    continue
                candidates.append(path)

        seen: set[str] = set()
        for candidate in sorted(candidates):
            relative = rel_path(candidate)
            if relative in seen:
                continue
            seen.add(relative)

            if not candidate.is_file():
                excluded.append(ExcludedEntry(path=relative, reason="not-file"))
                continue
            if self._allowed_extensions and candidate.suffix.lower() not in self._allowed_extensions:
                excluded.append(ExcludedEntry(path=relative, reason="extension"))
                continue

            try:
                size = candidate.stat().st_size
            except OSError:
                excluded.append(ExcludedEntry(path=relative, reason="stat-error"))
                continue

            preview = _read_text_preview(
                candidate,
                head_lines=self._preview_lines,
                max_bytes=self._max_bytes,
            )
            if preview is None:
                excluded.append(ExcludedEntry(path=relative, reason="preview-unavailable"))
                preview_text = ""
            else:
                preview_text = preview

            structure.append(
                WorkspaceEntry(
                    path=relative,
                    size=size,
                    preview=preview_text,
                    selected=relative in selected_relatives,
                )
            )

        bucket = context.setdefault("workspace", {})
        structure_dicts = [entry.to_dict() for entry in structure]
        bucket["structure"] = structure_dicts
        bucket["structure_excluded"] = [entry.to_dict() for entry in excluded]

        result = {
            "structure": structure_dicts,
            "excluded": bucket["structure_excluded"],
        }

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, structure_dicts)

        if self._excluded_path:
            scope, rel = _parse_target_expression(self._excluded_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, bucket["structure_excluded"])

        return result


__all__ = ["WorkspaceInspectorNode"]
