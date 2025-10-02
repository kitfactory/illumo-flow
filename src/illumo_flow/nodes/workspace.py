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


def _normalize_diff_path(value: str) -> str:
    base = value.split("\t", 1)[0]
    if base in {"/dev/null", "dev/null"}:
        return ""
    if base.startswith("a/") or base.startswith("b/"):
        return base[2:]
    return base


def _parse_unified_diff(diff_text: str) -> List[FilePatch]:
    lines = diff_text.splitlines()
    patches: List[FilePatch] = []
    idx = 0
    current_patch: Optional[FilePatch] = None

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("--- "):
            old_path = line[4:]
            idx += 1
            if idx >= len(lines) or not lines[idx].startswith("+++ "):
                raise FlowError("Malformed unified diff: expected '+++ ' line")
            new_path = lines[idx][4:]
            idx += 1

            normalized_new = _normalize_diff_path(new_path)
            normalized_old = _normalize_diff_path(old_path)
            current_patch = FilePatch(
                path=normalized_new or normalized_old,
                hunks=[],
                is_new_file=normalized_old == "",
                is_delete=normalized_new == "",
            )
            patches.append(current_patch)
            continue

        if line.startswith("@@ ") and current_patch is not None:
            header_parts = line.split()
            if len(header_parts) < 3:
                raise FlowError("Malformed hunk header in unified diff")
            old_range = header_parts[1]
            new_range = header_parts[2]
            try:
                old_start = int(old_range.split(",")[0][1:])
                new_start = int(new_range.split(",")[0][1:])
            except ValueError as exc:  # pragma: no cover - defensive
                raise FlowError("Invalid hunk range in unified diff") from exc

            idx += 1
            hunk_lines: List[str] = []
            no_newline = False
            while idx < len(lines):
                current = lines[idx]
                if current.startswith("@@ ") or current.startswith("--- "):
                    break
                if current.startswith("diff ") or current.startswith("index "):
                    break
                if current.startswith("\\ No newline at end of file"):
                    no_newline = True
                    idx += 1
                    continue
                hunk_lines.append(current)
                idx += 1

            current_patch.hunks.append(
                Hunk(old_start=old_start, new_start=new_start, lines=hunk_lines, no_newline_at_end=no_newline)
            )
            continue

        idx += 1

    return patches


def _apply_hunks(original_text: str, file_patch: FilePatch) -> str:
    original_lines = original_text.splitlines()
    result_lines: List[str] = []
    cursor = 0

    for hunk in file_patch.hunks:
        target_index = max(hunk.old_start - 1, 0)
        if target_index > len(original_lines):
            target_index = len(original_lines)
        result_lines.extend(original_lines[cursor:target_index])
        cursor = target_index

        for raw in hunk.lines:
            if not raw:
                continue
            marker = raw[0]
            content = raw[1:]
            if marker == " ":
                if cursor < len(original_lines):
                    result_lines.append(original_lines[cursor])
                else:
                    result_lines.append(content)
                cursor += 1
            elif marker == "-":
                if cursor < len(original_lines):
                    cursor += 1
            elif marker == "+":
                result_lines.append(content)
            else:
                raise FlowError(f"Unsupported diff marker '{marker}'")

    result_lines.extend(original_lines[cursor:])

    new_text = "\n".join(result_lines)
    needs_trailing_newline = not any(h.no_newline_at_end for h in file_patch.hunks)
    if needs_trailing_newline and (result_lines or original_text.endswith("\n")) and not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


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


@dataclass
class Hunk:
    old_start: int
    new_start: int
    lines: List[str]
    no_newline_at_end: bool = False


@dataclass
class FilePatch:
    path: str
    hunks: List[Hunk]
    is_new_file: bool = False
    is_delete: bool = False


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


class PatchNode(Node):
    """Apply unified diffs to workspace files without touching disk by default."""

    def __init__(self, *, config: NodeConfig) -> None:
        super().__init__(config=config)
        self._default_root = config.setting_value("default_root") or "."
        allowed = config.setting_value("allowed_paths")
        if isinstance(allowed, str):
            allowed = [allowed]
        self._allowed_paths = [Path(str(p)).as_posix() for p in (allowed or [])]
        self._output_path = config.setting_value("output_path")
        self._summary_path = config.setting_value("summary_path")

    def run(self, payload: Any) -> MutableMapping[str, Any]:  # type: ignore[override]
        context = self.request_context()
        request = context.setdefault("request", {})

        diff_text = None
        if isinstance(payload, str) and payload.strip():
            diff_text = payload
        elif isinstance(payload, MutableMapping) and "diff" in payload:
            diff_text = str(payload["diff"])
        else:
            diff_text = context.get("diff", {}).get("proposed")

        if not diff_text:
            raise FlowError("PatchNode requires a unified diff in payload or context['diff']['proposed']")

        root_setting = request.get("target_root") or self._default_root
        root_path = Path(root_setting).expanduser()
        if not root_path.is_absolute():
            root_path = Path.cwd() / root_path
        root_path = root_path.resolve()
        if not root_path.exists():
            raise FlowError(f"Workspace root '{root_path}' does not exist")

        patches = _parse_unified_diff(diff_text)
        if not patches:
            raise FlowError("PatchNode received an empty diff")

        workspace = context.setdefault("workspace", {})
        files_bucket = workspace.setdefault("files", [])
        indexed = {entry.get("path"): entry for entry in files_bucket if isinstance(entry, dict)}

        applied: List[dict[str, Any]] = []
        write_changes = bool(request.get("write"))

        for patch in patches:
            relative_path = patch.path
            if not relative_path:
                continue

            normalized = Path(relative_path)
            if normalized.is_absolute():
                candidate_path = normalized
            else:
                candidate_path = (root_path / normalized).resolve()

            if not _is_within_path(root_path, candidate_path):
                raise FlowError(f"Patch target '{relative_path}' escapes the workspace root")

            relative_posix = candidate_path.relative_to(root_path).as_posix()
            if self._allowed_paths and relative_posix not in self._allowed_paths:
                raise FlowError(f"Patch target '{relative_posix}' is not permitted")

            try:
                original_text = candidate_path.read_text(encoding="utf-8") if not patch.is_new_file else ""
            except OSError:
                if patch.is_new_file:
                    original_text = ""
                else:
                    raise FlowError(f"Unable to read original file '{relative_posix}'")

            if patch.is_delete:
                new_text = ""
                status = "deleted"
            else:
                new_text = _apply_hunks(original_text, patch)
                status = "added" if patch.is_new_file else "patched"

            if write_changes:
                if status == "deleted":
                    try:
                        candidate_path.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    candidate_path.parent.mkdir(parents=True, exist_ok=True)
                    candidate_path.write_text(new_text, encoding="utf-8")

            entry = indexed.get(relative_posix, {"path": relative_posix})
            entry["original_content"] = original_text
            entry["patched_content"] = new_text
            entry["status"] = status
            indexed[relative_posix] = entry
            applied.append({"path": relative_posix, "status": status})

        workspace["files"] = list(indexed.values())
        context.setdefault("diff", {})["applied"] = applied

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, workspace["files"])

        if self._summary_path:
            scope, rel = _parse_target_expression(self._summary_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, applied)

        return {"files": workspace["files"], "applied": applied}


__all__ = ["WorkspaceInspectorNode"]
