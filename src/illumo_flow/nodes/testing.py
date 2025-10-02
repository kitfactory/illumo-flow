"""Testing related nodes."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, List, MutableMapping, Optional

from ..core import FlowError, Node, NodeConfig, _parse_target_expression, _resolve_scope_mapping, _set_to_path


def _normalize_command(value: Any) -> List[str]:
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    raise FlowError("TestExecutorNode command must be a string or iterable of strings")


class TestExecutorNode(Node):
    """Execute shell commands (typically pytest) and capture the results."""

    DEFAULT_TIMEOUT = 120.0

    def __init__(self, *, config: NodeConfig) -> None:
        super().__init__(config=config)
        self._default_root = config.setting_value("default_root") or "."
        self._default_command = config.setting_value("command")
        timeout = config.setting_value("timeout")
        self._timeout = float(timeout) if timeout is not None else self.DEFAULT_TIMEOUT
        env_mapping = config.setting_value("env") or {}
        if not isinstance(env_mapping, MutableMapping):
            raise FlowError("TestExecutorNode 'env' setting must be a mapping of environment variables")
        self._env = {str(key): str(value) for key, value in env_mapping.items()}
        self._output_path = config.setting_value("output_path")

    def run(self, payload: Any) -> MutableMapping[str, Any]:  # type: ignore[override]
        context = self.request_context()
        request = context.setdefault("request", {})
        tests_bucket = context.setdefault("tests", {})

        command_value = tests_bucket.get("command") or request.get("tests") or self._default_command
        if not command_value:
            raise FlowError("TestExecutorNode requires a command to execute")
        command = _normalize_command(command_value)

        root_setting = request.get("target_root") or self._default_root
        root_path = Path(root_setting).expanduser()
        if not root_path.is_absolute():
            root_path = Path.cwd() / root_path
        root_path = root_path.resolve()
        if not root_path.exists():
            raise FlowError(f"Test workspace '{root_path}' does not exist")

        env = os.environ.copy()
        env.update(self._env)

        pythonpath = env.get("PYTHONPATH")
        root_str = str(root_path)
        if pythonpath:
            if root_str not in pythonpath.split(os.pathsep):
                env["PYTHONPATH"] = os.pathsep.join([pythonpath, root_str])
        else:
            env["PYTHONPATH"] = root_str

        start = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=str(root_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        duration = time.monotonic() - start

        result = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration": duration,
            "cwd": str(root_path),
        }

        tests_bucket["results"] = result

        if self._output_path:
            scope, rel = _parse_target_expression(self._output_path)
            target = _resolve_scope_mapping(context, scope)
            _set_to_path(target, rel, result)

        return result


__all__ = ["TestExecutorNode"]
