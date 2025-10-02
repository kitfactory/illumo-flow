from __future__ import annotations

import difflib
import shlex
import sys
from pathlib import Path

import pytest

from illumo_flow.core import FlowError, NodeConfig
from illumo_flow.nodes.summary import SummaryAgent
from illumo_flow.nodes.testing import TestExecutorNode
from illumo_flow.nodes.workspace import PatchNode, WorkspaceInspectorNode


def build_node(**settings: object) -> WorkspaceInspectorNode:
    config = NodeConfig(name="workspace_inspector", setting=settings)
    node = WorkspaceInspectorNode(config=config)
    node.bind("workspace_inspector")
    return node


def run_node(node: WorkspaceInspectorNode, context: dict) -> dict:
    result = node._execute({}, context)  # type: ignore[arg-type]
    return result


def build_patch_node(**settings: object) -> PatchNode:
    config = NodeConfig(name="patch_node", setting=settings)
    node = PatchNode(config=config)
    node.bind("patch_node")
    return node


def run_patch(node: PatchNode, context: dict, diff: str) -> dict:
    return node._execute(diff, context)  # type: ignore[arg-type]


def build_test_executor_node(**settings: object) -> TestExecutorNode:
    config = NodeConfig(name="test_executor", setting=settings)
    node = TestExecutorNode(config=config)
    node.bind("test_executor")
    return node


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


def make_diff(original: str, updated: str, filename: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=filename,
            tofile=filename,
            lineterm="",
        )
    )


def test_patch_node_applies_diff_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "sample.py"
    original = "def add(a, b):\n    return a - b\n"
    updated = "def add(a, b):\n    return a + b\n"
    target.write_text(original)

    diff = make_diff(original, updated, "sample.py")
    context = {"request": {"target_root": str(root)}, "diff": {"proposed": diff}}

    node = build_patch_node()
    result = run_patch(node, context, diff)

    files = result["files"]
    entry = next(item for item in files if item["path"] == "sample.py")
    assert entry["original_content"] == original
    assert entry["patched_content"] == updated
    assert entry["status"] == "patched"
    # ensure original file not modified without --write
    assert target.read_text() == original


def test_patch_node_respects_allowed_paths(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "sample.py"
    target.write_text("print('ok')\n")

    diff = make_diff("print('ok')\n", "print('updated')\n", "sample.py")
    context = {"request": {"target_root": str(root)}, "diff": {"proposed": diff}}
    node = build_patch_node(allowed_paths=["sample.py"])
    run_patch(node, context, diff)

    with pytest.raises(FlowError):
        node_restricted = build_patch_node(allowed_paths=["other.py"])
        run_patch(node_restricted, context, diff)


def test_patch_node_write_option(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "app.py"
    original = "value = 1\n"
    updated = "value = 2\n"
    target.write_text(original)

    diff = make_diff(original, updated, "app.py")
    context = {
        "request": {"target_root": str(root), "write": True},
        "diff": {"proposed": diff},
    }
    node = build_patch_node()
    run_patch(node, context, diff)

    assert target.read_text() == updated


def build_summary_agent(**settings: object) -> SummaryAgent:
    config = NodeConfig(name="summary_agent", setting=settings)
    node = SummaryAgent(config=config)
    node.bind("summary_agent")
    return node


def test_test_executor_runs_pytest(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    root.mkdir()
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_add():\n    assert 1 + 1 == 2\n")

    context = {
        "request": {"target_root": str(root)},
        "tests": {"command": "pytest -q"},
    }

    node = build_test_executor_node(timeout=30)
    result = node._execute(None, context)  # type: ignore[arg-type]

    assert result["returncode"] == 0
    assert "tests" in context and context["tests"]["results"]["returncode"] == 0


def test_test_executor_records_failures(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    root.mkdir()

    context = {
        "request": {"target_root": str(root)},
        "tests": {"command": f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(1)'"},
    }

    node = build_test_executor_node(timeout=5)
    result = node._execute(None, context)  # type: ignore[arg-type]

    assert result["returncode"] == 1
    assert context["tests"]["results"]["returncode"] == 1


def test_summary_agent_compiles_report() -> None:
    context = {
        "workspace": {
            "files": [
                {"path": "sample.py", "status": "patched", "original_content": "a", "patched_content": "b"}
            ]
        },
        "tests": {
            "results": {
                "command": ["pytest", "-q"],
                "returncode": 0,
                "stdout": "1 passed in 0.01s\n",
                "stderr": "",
            }
        },
        "review": {"summary": "Looks good", "status": "OK"},
    }

    node = build_summary_agent()
    result = node._execute(None, context)  # type: ignore[arg-type]

    assert "### Files" in result["report"]
    assert "sample.py" in result["report"]
    assert context["summary"]["report"] == result["report"]
    assert context["summary"]["structured"]["files"]
