# SPDX-License-Identifier: MIT
"""Shared launcher utilities for command-line wrappers."""

from __future__ import annotations

import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
CACHE_DIR = PROJECT_ROOT / ".lint-cache"
UV_CACHE_DIR = CACHE_DIR / "uv"
PYTHON_OVERRIDE_ENV = "PYQA_PYTHON"
UV_COMMAND_ENV = "PYQA_UV"
VERBOSE_ENV = "PYQA_WRAPPER_VERBOSE"
MIN_PYTHON = (3, 12)


def launch(command: str, argv: Iterable[str] | None = None) -> None:
    """Launch a pyqa CLI command, favouring local environments first."""

    args = list(sys.argv[1:] if argv is None else argv)
    selected = _select_interpreter()
    env = _build_env(selected)

    if _probe_interpreter(selected, env):
        _run_with_python(selected, command, args, env)
    else:
        uv_path = _ensure_uv()
        _run_with_uv(uv_path, command, args)


def _debug(message: str) -> None:
    if os.environ.get(VERBOSE_ENV):
        print(message, file=sys.stderr)


def _select_interpreter() -> Path:
    override = os.environ.get(PYTHON_OVERRIDE_ENV)
    if override:
        path = Path(shutil.which(override) or override).expanduser().resolve()
        if not path.exists():
            print(f"PYQA_PYTHON interpreter not found: {path}", file=sys.stderr)
            sys.exit(1)
        _debug(f"Using PYQA_PYTHON interpreter: {path}")
        return path

    repo_python = (PROJECT_ROOT / ".venv" / "bin" / "python").resolve()
    if repo_python.exists():
        _debug(f"Using repository virtualenv interpreter: {repo_python}")
        return repo_python

    current = Path(sys.executable).resolve()
    _debug(f"Using current interpreter: {current}")
    return current


def _build_env(python_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    src_str = str(SRC_DIR)
    if src_str not in parts:
        env["PYTHONPATH"] = os.pathsep.join([src_str, *parts]) if parts else src_str
    return env


def _probe_interpreter(python_path: Path, env: dict[str, str]) -> bool:
    if not _is_python_version_compatible(python_path):
        _debug("Interpreter version too old; will use uv fallback.")
        return False
    try:
        result = subprocess.run(
            [str(python_path), "-c", PROBE_SCRIPT],
            env=env,
            check=True,
            capture_output=True,
        )
        probe_result = result.stdout.decode().strip()
        _debug(f"Probe result: {probe_result}")
        return probe_result == "ok"
    except subprocess.CalledProcessError as exc:  # pragma: no cover - probe failure
        _debug(f"Probe failed: {exc.stderr.decode().strip()}" if exc.stderr else str(exc))
        return False


def _is_python_version_compatible(python_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.version_info[:2])"],
            check=True,
            capture_output=True,
        )
        version_tuple = eval(result.stdout.decode().strip())
        compatible = version_tuple >= MIN_PYTHON
        if not compatible:
            _debug(f"Interpreter {python_path} version {version_tuple} < {MIN_PYTHON}.")
        return compatible
    except Exception as exc:  # pragma: no cover - rare
        _debug(f"Version probe failed: {exc}")
        return False


def _run_with_python(executable: Path, command: str, args: list[str], env: dict[str, str]) -> None:
    _debug(f"Running with local interpreter: {executable}")
    argv_payload = [command, *args]
    code = """
import sys
from typer.main import get_command
from pyqa.cli.app import app as _app
argv = {argv!r}
command = get_command(_app)
command.main(args=argv, prog_name='pyqa')
""".format(argv=argv_payload)
    result = subprocess.run([str(executable), "-c", code], env=env)
    sys.exit(result.returncode)


def _run_with_uv(uv_path: Path, command: str, args: list[str]) -> None:
    _debug(f"Running with uv: {uv_path}")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    argv_payload = [command, *args]
    code = """
import sys
from typer.main import get_command
from pyqa.cli.app import app as _app
argv = {argv!r}
command = get_command(_app)
command.main(args=argv, prog_name='pyqa')
""".format(argv=argv_payload)
    cmd = [
        str(uv_path),
        "--project",
        str(PROJECT_ROOT),
        "run",
        "python",
        "-c",
        code,
    ]
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


def _ensure_uv() -> Path:
    override = os.environ.get(UV_COMMAND_ENV)
    if override:
        path = Path(shutil.which(override) or override).expanduser().resolve()
        if not path.exists():
            print(f"PYQA_UV executable not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    found = shutil.which("uv")
    if found:
        return Path(found)

    return _download_uv_binary()


def _download_uv_binary() -> Path:
    triple = _detect_uv_triple()
    target_dir = UV_CACHE_DIR / triple
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "uv"
    if target.exists():
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
        return target

    url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{triple}.tar.gz"
    _debug(f"Downloading uv from {url}")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()
    except OSError as exc:
        print(f"Failed to download uv: {exc}", file=sys.stderr)
        sys.exit(1)

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(target_dir)

    for candidate in target_dir.rglob("uv"):
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | stat.S_IEXEC)
            if candidate != target:
                try:
                    candidate.rename(target)
                except OSError:
                    target.write_bytes(candidate.read_bytes())
            return target

    print("Downloaded uv but could not locate the binary.", file=sys.stderr)
    sys.exit(1)


def _detect_uv_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "x86_64-unknown-linux-gnu"
        if machine in {"aarch64", "arm64"}:
            return "aarch64-unknown-linux-gnu"
    if system == "darwin":
        if machine in {"x86_64", "amd64"}:
            return "x86_64-apple-darwin"
        if machine in {"arm64", "aarch64"}:
            return "aarch64-apple-darwin"
    print(f"Unsupported platform for uv auto-download: {system}/{machine}", file=sys.stderr)
    sys.exit(1)


PROBE_SCRIPT = """
import importlib
import sys
from pathlib import Path

SRC = Path({src!r}).resolve()

try:
    pyqa = importlib.import_module('pyqa')
    cli = importlib.import_module('pyqa.cli')
    app = importlib.import_module('pyqa.cli.app')
except Exception:
    print('missing', end='')
    sys.exit(0)

for module in (pyqa, cli, app):
    module_file = getattr(module, '__file__', None)
    if not module_file:
        print('outside', end='')
        sys.exit(0)
    path = Path(module_file).resolve()
    try:
        path.relative_to(SRC)
    except ValueError:
        print('outside', end='')
        sys.exit(0)

print('ok', end='')
""".format(src=str(SRC_DIR))

__all__ = ["launch"]
