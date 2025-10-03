# SPDX-License-Identifier: MIT
"""Step definitions for CLI wrapper behaviours."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

from pytest_bdd import given, parsers, then, when

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_ENV: Dict[str, str] = {}
RESULT: Dict[str, Optional[subprocess.CompletedProcess[str]]] = {"process": None}
ARTIFACT_ROOT: Path | None = None


@given("the project root is set to the current repository")
def set_project_root(tmp_path: Path) -> None:  # noqa: B018
    WRAPPER_ENV.clear()
    WRAPPER_ENV.update(os.environ)
    WRAPPER_ENV.setdefault("PYTHONPATH", f"{PROJECT_ROOT / 'src'}")
    WRAPPER_ENV["PYQA_WRAPPER_VERBOSE"] = "1"
    global ARTIFACT_ROOT
    ARTIFACT_ROOT = tmp_path / "wrapper-artifacts"
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)


@given("the repository virtualenv is available")
def ensure_repo_venv() -> None:
    python_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not python_path.exists():
        raise RuntimeError(f"Expected virtualenv python at {python_path}")


@given(parsers.parse('PYQA_PYTHON points to "{path}"'))
def set_pyqa_python(path: str) -> None:
    resolved = _resolve_artifact(path)
    WRAPPER_ENV["PYQA_PYTHON"] = str(resolved)


@given(parsers.parse('PYQA_UV points to "{path}"'))
def set_pyqa_uv(path: str) -> None:
    resolved = _resolve_artifact(path)
    WRAPPER_ENV["PYQA_UV"] = str(resolved)


@when(parsers.parse('I run the "{wrapper}" wrapper with "{args}"'))
def run_wrapper(wrapper: str, args: str) -> None:
    command = [str(PROJECT_ROOT / wrapper), *filter(None, args.split())]
    RESULT["process"] = subprocess.run(
        command,
        env=WRAPPER_ENV,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


@then(parsers.parse("the wrapper exits with status {code:d}"))
def assert_exit_code(code: int) -> None:
    process = RESULT["process"]
    assert process is not None
    assert process.returncode == code, process.stderr


@then("the wrapper uses the local interpreter")
def assert_local_interpreter() -> None:
    process = RESULT["process"]
    assert process is not None
    stderr = process.stderr
    assert "Using repository virtualenv interpreter" in stderr
    assert "Running with local interpreter" in stderr


@then("the wrapper falls back to uv")
def assert_uv_fallback() -> None:
    process = RESULT["process"]
    assert process is not None
    stderr = process.stderr
    assert "will use uv fallback" in stderr or "Running with uv" in stderr


@then("the wrapper reports a missing uv tool")
def assert_missing_uv() -> None:
    process = RESULT["process"]
    assert process is not None
    stderr = process.stderr
    assert "PYQA_UV executable not found" in stderr


def _resolve_artifact(path: str) -> Path:
    if Path(path).is_absolute():
        return Path(path)
    if ARTIFACT_ROOT is None:
        raise RuntimeError("Artifact root is not initialised")
    target = (ARTIFACT_ROOT / path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".py":
        script = _python_stub_for(target.name)
        target.write_text(script, encoding="utf-8")
        target.chmod(0o755)
    elif target.suffix in {"", ".sh"}:
        script = _shell_stub_for(target.name)
        target.write_text(script, encoding="utf-8")
        target.chmod(0o755)
    else:
        target.touch()
    return target


def _python_stub_for(name: str) -> str:
    if "py311" in name:
        return (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "code = args[1] if args and args[0] == '-c' else ''\n"
            "if 'sys.version_info' in code:\n"
            "    print('(3, 11)')\n"
            "else:\n"
            "    print('missing', end='')\n"
        )
    if "py_outside" in name:
        return (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "code = args[1] if args and args[0] == '-c' else ''\n"
            "if 'sys.version_info' in code:\n"
            "    print('(3, 12)')\n"
            "else:\n"
            "    print('outside', end='')\n"
        )
    raise ValueError(f"Unknown python stub requested: {name}")


def _shell_stub_for(name: str) -> str:
    if "fake_uv" in name:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo \"fake uv invoked with args: $*\" >&2\n"
            "exit 0\n"
        )
    raise ValueError(f"Unknown shell stub requested: {name}")
