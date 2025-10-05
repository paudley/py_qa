# SPDX-License-Identifier: MIT
"""Shared launcher utilities for command-line wrappers.

This module previously lived under ``scripts/cli_launcher.py``; relocating it
within :mod:`pyqa.cli` keeps all CLI-related helpers in the package namespace
while preserving the import contract for entry-point shims.
"""

from __future__ import annotations

import ast
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Final

PYQA_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SRC_DIR: Final[Path] = PYQA_ROOT / "src"
CACHE_DIR: Final[Path] = PYQA_ROOT / ".lint-cache"
UV_CACHE_DIR: Final[Path] = CACHE_DIR / "uv"
PYTHON_OVERRIDE_ENV: Final[str] = "PYQA_PYTHON"
UV_COMMAND_ENV: Final[str] = "PYQA_UV"
VERBOSE_ENV: Final[str] = "PYQA_WRAPPER_VERBOSE"
DEPENDENCY_SENTINEL: Final[str] = "PYQA_LAUNCHER_IMPORT_ERROR::"
DEPENDENCY_FLAG_ENV: Final[str] = "PYQA_LAUNCHER_EXPECT_DEPENDENCIES"
DEPENDENCY_EXIT_CODE: Final[int] = 97
MIN_PYTHON: Final[tuple[int, int]] = (3, 12)
PROG_NAME: Final[str] = "pyqa"
VERSION_COMPONENTS: Final[int] = 2


class ProbeStatus(StrEnum):
    """Probe outcomes when validating an interpreter."""

    OK = "ok"
    OUTSIDE = "outside"
    MISSING = "missing"


ARCH_ALIASES: Final[dict[str, str]] = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}

UV_TRIPLES: Final[dict[tuple[str, str], str]] = {
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("darwin", "aarch64"): "aarch64-apple-darwin",
}


class ProbeError(RuntimeError):
    """Raised when probing an interpreter fails."""


PROBE_SCRIPT: Final[str] = (
    "import importlib\n"
    "import sys\n"
    "from pathlib import Path\n\n"
    f"SRC = Path({str(SRC_DIR)!r}).resolve()\n\n"
    "try:\n"
    "    pyqa = importlib.import_module('pyqa')\n"
    "    cli = importlib.import_module('pyqa.cli')\n"
    "    app = importlib.import_module('pyqa.cli.app')\n"
    "except Exception:\n"
    f"    print('{ProbeStatus.MISSING.value}', end='')\n"
    "    sys.exit(0)\n\n"
    "for module in (pyqa, cli, app):\n"
    "    module_file = getattr(module, '__file__', None)\n"
    "    if not module_file:\n"
    f"        print('{ProbeStatus.OUTSIDE.value}', end='')\n"
    "        sys.exit(0)\n"
    "    path = Path(module_file).resolve()\n"
    "    try:\n"
    "        path.relative_to(SRC)\n"
    "    except ValueError:\n"
    f"        print('{ProbeStatus.OUTSIDE.value}', end='')\n"
    "        sys.exit(0)\n\n"
    f"print('{ProbeStatus.OK.value}', end='')\n"
)

__all__ = ["launch"]


def launch(command: str, argv: Iterable[str] | None = None) -> None:
    """Launch a pyqa CLI command, favouring the repository environment.

    Args:
        command: The Typer sub-command to invoke (for example ``"lint"``).
        argv: Optional sequence of additional arguments. When ``None`` the
            arguments from :data:`sys.argv` (excluding the script name) are
            forwarded.

    Returns:
        None
    """

    args = list(sys.argv[1:] if argv is None else argv)
    interpreter = _select_interpreter()
    env = _build_env(interpreter)

    if _probe_interpreter(interpreter, env):
        _run_with_python(interpreter, command, args, env)
        return

    uv_path = _ensure_uv()
    _run_with_uv(uv_path, command, args, require_locked=True)


def _debug(message: str) -> None:
    """Emit a debug message when wrapper verbosity is enabled.

    Args:
        message: Human-readable details to emit.
    """

    if os.environ.get(VERBOSE_ENV):
        print(message, file=sys.stderr)


def _select_interpreter() -> Path:
    """Return the interpreter that should execute the CLI."""

    override = os.environ.get(PYTHON_OVERRIDE_ENV)
    if override:
        path = Path(shutil.which(override) or override).expanduser()
        if not path.exists():
            print(f"PYQA_PYTHON interpreter not found: {path}", file=sys.stderr)
            sys.exit(1)
        _debug(f"Using PYQA_PYTHON interpreter: {path}")
        return path

    repo_python = (PYQA_ROOT / ".venv" / "bin" / "python").expanduser()
    if repo_python.exists():
        _debug(f"Using repository virtualenv interpreter: {repo_python}")
        return repo_python

    current = Path(sys.executable).expanduser()
    _debug(f"Using current interpreter: {current}")
    return current


def _build_env(python_path: Path) -> dict[str, str]:
    """Return an environment mapping with repository ``src`` on the path."""

    env = os.environ.copy()
    env["PYQA_SELECTED_PYTHON"] = str(python_path)

    existing = env.get("PYTHONPATH", "")
    src_path = str(SRC_DIR)
    parts = [segment for segment in existing.split(os.pathsep) if segment]
    updated_paths: list[str] = list(parts)

    candidate_roots = [PYQA_ROOT / ".venv" / "lib", PYQA_ROOT / ".venv" / "Lib"]
    for base in candidate_roots:
        if not base.exists():
            _debug(f"Skipping missing site-packages root for PYTHONPATH: {base}")
            continue
        for site_packages in base.glob("python*/site-packages"):
            site_str = str(site_packages)
            if site_str not in updated_paths:
                updated_paths.insert(0, site_str)
                _debug(f"Prepended site-packages to PYTHONPATH: {site_packages}")

    if src_path not in updated_paths:
        updated_paths.insert(0, src_path)
        _debug(f"Prepended src directory to PYTHONPATH: {SRC_DIR}")
    else:
        _debug(f"Src directory already present on PYTHONPATH: {SRC_DIR}")

    env["PYTHONPATH"] = os.pathsep.join(updated_paths)

    python_dir = str(python_path.parent)
    path_parts = [segment for segment in env.get("PATH", "").split(os.pathsep) if segment]
    if python_dir and python_dir not in path_parts:
        env["PATH"] = os.pathsep.join([python_dir, *path_parts]) if path_parts else python_dir
        _debug(f"Prepended interpreter bin directory to PATH: {python_dir}")
    else:
        _debug(f"Interpreter bin directory already present on PATH: {python_dir}")

    return env


def _probe_interpreter(python_path: Path, env: dict[str, str]) -> bool:
    """Return ``True`` when ``python_path`` can import pyqa from ``src``."""

    if not _is_python_version_compatible(python_path):
        _debug("Interpreter version too old; will use uv fallback.")
        return False

    try:
        completed = subprocess.run(
            [str(python_path), "-c", PROBE_SCRIPT],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - subprocess failure path
        _debug(f"Interpreter probe failed: {exc}")
        return False

    status = completed.stdout.strip() or ProbeStatus.MISSING.value
    _debug(f"Probe status: {status}")
    return status == ProbeStatus.OK.value


def _is_python_version_compatible(python_path: Path) -> bool:
    """Return whether ``python_path`` reports a compatible version."""

    try:
        output = subprocess.check_output([str(python_path), "-c", "import sys; print(sys.version_info[:2])"])
        version_info = ast.literal_eval(output.decode().strip())
    except (subprocess.CalledProcessError, OSError, ValueError, SyntaxError):
        _debug("Unable to determine interpreter version; assuming incompatible.")
        return False
    major, minor = version_info
    minimum_major, minimum_minor = MIN_PYTHON
    compatible = (major, minor) >= (minimum_major, minimum_minor)
    _debug(f"Interpreter version check: {(major, minor)} >= {(minimum_major, minimum_minor)} -> {compatible}")
    return compatible


def _run_with_python(
    python_path: Path,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> None:
    """Execute ``command`` using ``python_path`` within the repository environment."""

    current_executable = Path(sys.executable).resolve()
    selected_executable = python_path.resolve()
    _debug(
        "Evaluating interpreter for in-process execution: current=%s selected=%s"
        % (current_executable, selected_executable)
    )

    if current_executable == selected_executable:
        _debug("Using current interpreter for in-process execution")
        try:
            from pyqa.cli.app import app
        except ModuleNotFoundError as exc:
            _debug("Local interpreter missing dependencies; falling back to uv: " f"{exc.__class__.__name__}: {exc}")
            uv_path = _ensure_uv()
            _run_with_uv(uv_path, command, args, require_locked=True)
            return

        sys.argv = [PROG_NAME, command, *args]
        os.environ.update(env)
        app()
        return

    _debug("Spawning separate interpreter for CLI execution")
    code = _build_cli_invocation_code([command, *args])
    execution_cmd = [str(python_path), "-c", code]
    spawn_env = env.copy()
    spawn_env[DEPENDENCY_FLAG_ENV] = "1"
    _debug(f"Executing command: {execution_cmd}")
    result = subprocess.run(
        execution_cmd,
        env=spawn_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    missing_dependency = result.returncode == DEPENDENCY_EXIT_CODE or (
        result.stderr and DEPENDENCY_SENTINEL in result.stderr
    )
    if missing_dependency:
        _debug("Detected dependency import failure from spawned interpreter; rerunning via uv with --locked")
        uv_path = _ensure_uv()
        _run_with_uv(uv_path, command, args, require_locked=True)
        return

    _debug(f"Interpreter exited with return code {result.returncode}")
    sys.exit(result.returncode)


def _ensure_uv() -> Path:
    """Return the ``uv`` executable, downloading it when required."""

    override = os.environ.get(UV_COMMAND_ENV)
    if override:
        resolved = Path(shutil.which(override) or override).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"uv override not found: {resolved}")
        return resolved

    candidate_paths = [
        PYQA_ROOT / ".venv" / "bin" / "uv",
        Path(shutil.which("uv") or ""),
    ]
    for candidate in candidate_paths:
        if candidate and candidate.exists() and os.access(candidate, os.X_OK):
            _debug(f"Using existing uv executable: {candidate}")
            return candidate

    UV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = UV_CACHE_DIR / "uv"
    if target.exists():
        _debug(f"Reusing cached uv executable: {target}")
        return target

    system = platform.system().lower()
    machine = ARCH_ALIASES.get(platform.machine().lower())
    if not machine:
        raise ProbeError(f"Unsupported architecture: {platform.machine()}")

    triple = UV_TRIPLES.get((system, machine))
    if not triple:
        raise ProbeError(f"Unsupported platform: {system}-{machine}")

    archive_name = f"uv-{triple}.tar.gz"
    url = f"https://github.com/astral-sh/uv/releases/latest/download/{archive_name}"
    _debug(f"Downloading uv from {url}")
    archive_path = UV_CACHE_DIR / archive_name
    with urllib.request.urlopen(url) as response, open(archive_path, "wb") as handle:
        shutil.copyfileobj(response, handle)

    extracted_name: str | None = None
    with tarfile.open(archive_path, "r:gz") as tar:
        binary_member = next((member for member in tar.getmembers() if member.name.endswith("/uv")), None)
        if binary_member is None:
            raise ProbeError("uv binary not found in archive")
        extracted_name = binary_member.name
        tar.extract(binary_member, path=UV_CACHE_DIR)

    if extracted_name is None:  # pragma: no cover - defensive guard
        raise ProbeError("uv archive extraction produced no binary name")

    extracted_path = UV_CACHE_DIR / extracted_name
    final_path = target
    extracted_path.rename(final_path)
    extracted_parent = extracted_path.parent
    if extracted_parent != UV_CACHE_DIR and extracted_parent.exists():
        shutil.rmtree(extracted_parent)

    final_path.chmod(final_path.stat().st_mode | stat.S_IEXEC)
    return target


def _run_with_uv(
    uv_path: Path,
    command: str,
    args: list[str],
    *,
    require_locked: bool = False,
) -> None:
    """Execute ``command`` using ``uv`` when a local interpreter is unsuitable."""

    _debug(f"Running with uv: {uv_path}")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    code = _build_cli_invocation_code([command, *args])
    cmd = [str(uv_path), "--project", str(PYQA_ROOT), "run"]
    if require_locked:
        cmd.append("--locked")
        _debug("Including --locked to install/update dependencies via uv")
    cmd.extend(["python", "-c", code])
    _debug(f"Executing via uv: {cmd}")
    result = subprocess.run(cmd, env=env, check=False)
    _debug(f"uv execution completed with return code {result.returncode}")
    sys.exit(result.returncode)


def _build_cli_invocation_code(argv_payload: Iterable[str]) -> str:
    """Return a Python snippet that executes the Typer command directly."""

    argv_list = list(argv_payload)
    return (
        "import os\n"
        "import sys\n"
        "from typer.main import get_command\n"
        "try:\n"
        "    from pyqa.cli.app import app as _app\n"
        "except ModuleNotFoundError as exc:\n"
        f"    if os.environ.get('{DEPENDENCY_FLAG_ENV}'):\n"
        f"        sys.stderr.write('{DEPENDENCY_SENTINEL}' + exc.__class__.__name__ + ':' + str(exc) + '\\n')\n"
        f"        sys.exit({DEPENDENCY_EXIT_CODE})\n"
        "    raise\n"
        f"argv = {argv_list!r}\n"
        "command = get_command(_app)\n"
        f"command.main(args=argv, prog_name={PROG_NAME!r})\n"
    )
