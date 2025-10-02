from __future__ import annotations

from pathlib import Path

import pytest

from illumo_flow.core import FlowError, NodeConfig
from illumo_flow.nodes.workspace import WorkspaceInspectorNode


def build_node(**settings: object) -> WorkspaceInspectorNode:
    config = NodeConfig(name="workspace_inspector", setting=settings)
    node = WorkspaceInspectorNode(config=config)
    node.bind("workspace_inspector")
    return node


def run_node(node: WorkspaceInspectorNode, context: dict) -> dict:
    result = node._execute({}, context)  # type: ignore[arg-type]
    return result


def test_workspace_inspector_collects_selected_files(tmp_path: Path) -> None:
    sample = tmp_path / "sample_app"
    sample.mkdir()
    (sample / "module.py").write_text("""def add(a, b):\n    return a + b\n""")
    (sample / "README.md").write_text("# Sample App\n")

    context = {
        "request": {
            "target_root": str(sample),
            "target_files": ["module.py"],
        }
    }

    node = build_node()
    result = run_node(node, context)

    structure = result["structure"]
    assert any(entry["selected"] for entry in structure)
    module_entry = next(entry for entry in structure if entry["path"] == "module.py")
    assert module_entry["preview"].startswith("def add")
    assert context["workspace"]["structure"] == structure


def test_workspace_inspector_filters_by_extension(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "keep.py").write_text("print('ok')\n")
    (root / "drop.log").write_text("ignored\n")

    context = {"request": {"target_root": str(root)}}
    node = build_node(allowed_extensions=[".py"])
    result = run_node(node, context)

    structure = result["structure"]
    assert [entry["path"] for entry in structure] == ["keep.py"]
    excluded = result["excluded"]
    assert any(item["path"] == "drop.log" and item["reason"] == "extension" for item in excluded)


def test_workspace_inspector_respects_max_bytes(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    big_file = root / "large.py"
    big_file.write_text("x = 'a' * 1024\n")

    node = build_node(max_bytes=4)
    context = {"request": {"target_root": str(root)}}
    result = run_node(node, context)

    entry = result["structure"][0]
    assert entry["preview"] == ""
    excluded = result["excluded"]
    assert excluded and excluded[0]["reason"] == "preview-unavailable"


def test_workspace_inspector_rejects_missing_root(tmp_path: Path) -> None:
    node = build_node()
    context = {"request": {"target_root": str(tmp_path / "missing")}}
    with pytest.raises(FlowError):
        run_node(node, context)
