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
PATH_TRAVERSAL_COMPONENT: Final[str] = ".."


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
        major, minor = _read_python_version_info(python_path)
    except (ProbeError, subprocess.CalledProcessError, OSError, ValueError, SyntaxError):
        _debug("Unable to determine interpreter version; assuming incompatible.")
        return False
    minimum_major, minimum_minor = MIN_PYTHON
    compatible = (major, minor) >= (minimum_major, minimum_minor)
    _debug(f"Interpreter version check: {(major, minor)} >= {(minimum_major, minimum_minor)} -> {compatible}")
    return compatible


def _read_python_version_info(python_path: Path) -> tuple[int, int]:
    """Return the interpreter ``major`` and ``minor`` version numbers.

    Args:
        python_path: Executable resolving to the interpreter being probed.

    Returns:
        tuple[int, int]: The interpreter ``(major, minor)`` pair.

    Raises:
        ProbeError: If the interpreter reports an unexpected version payload.
    """

    output = subprocess.check_output([str(python_path), "-c", "import sys; print(sys.version_info[:2])"])
    text = output.decode().strip()
    parsed = ast.literal_eval(text)
    if not (isinstance(parsed, tuple) and len(parsed) == VERSION_COMPONENTS):
        raise ProbeError(f"Unexpected version payload from interpreter: {text}")
    major, minor = parsed
    if not (isinstance(major, int) and isinstance(minor, int)):
        raise ProbeError(f"Interpreter returned non-integer version data: {parsed!r}")
    return major, minor


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
        f"Evaluating interpreter for in-process execution: current={current_executable} "
        f"selected={selected_executable}"
    )

    if current_executable == selected_executable:
        _debug("Using current interpreter for in-process execution")
        _debug("Running with local interpreter")
        try:
            # Importing inside the execution branch lets us detect missing optional
            # dependencies and trigger the uv fallback without crashing at module
            # import time. pylint: disable=import-outside-toplevel
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
    with subprocess.Popen(
        execution_cmd,
        env=spawn_env,
        stdout=None,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        stderr_output = process.communicate()[1]
        if stderr_output:
            sys.stderr.write(stderr_output)
        missing_dependency = process.returncode == DEPENDENCY_EXIT_CODE or (
            stderr_output and DEPENDENCY_SENTINEL in stderr_output
        )
    if missing_dependency:
        _debug("Detected dependency import failure from spawned interpreter; rerunning via uv with --locked")
        uv_path = _ensure_uv()
        _run_with_uv(uv_path, command, args, require_locked=True)
        return

    _debug(f"Interpreter exited with return code {process.returncode}")
    sys.exit(process.returncode)


def _ensure_uv() -> Path:
    """Return the ``uv`` executable, downloading it when required.

    Returns:
        Path: Location of the ``uv`` executable ready for invocation.
    """

    override = _resolve_uv_override()
    if override is not None:
        return override

    existing = _find_existing_uv_path()
    if existing is not None:
        _debug(f"Using existing uv executable: {existing}")
        return existing

    UV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = UV_CACHE_DIR / "uv"
    if cached.exists():
        _debug(f"Reusing cached uv executable: {cached}")
        return cached

    archive_path = _download_uv_archive()
    final_path = _extract_uv_binary(archive_path)
    final_path.chmod(final_path.stat().st_mode | stat.S_IEXEC)
    return final_path


def _resolve_uv_override() -> Path | None:
    """Return the user-specified ``uv`` override when provided.

    Returns:
        Path | None: Resolved override path when the environment variable is
        set, otherwise ``None``.

    Raises:
        FileNotFoundError: If the override path does not exist on disk.
    """

    override = os.environ.get(UV_COMMAND_ENV)
    if not override:
        return None
    resolved = Path(shutil.which(override) or override).expanduser()
    if not resolved.exists():
        message = f"PYQA_UV executable not found: {resolved}"
        _debug(message)
        raise FileNotFoundError(message)
    return resolved


def _find_existing_uv_path() -> Path | None:
    """Return an already-installed ``uv`` executable when available.

    Returns:
        Path | None: Executable path when a suitable ``uv`` binary is found,
        otherwise ``None``.
    """

    bin_candidate = shutil.which("uv")
    candidates = [PYQA_ROOT / ".venv" / "bin" / "uv"]
    if bin_candidate:
        candidates.append(Path(bin_candidate))
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _download_uv_archive() -> Path:
    """Download the ``uv`` archive for the active platform into the cache.

    Returns:
        Path: Location of the downloaded archive within the cache directory.
    """

    triple = _resolve_uv_triple()
    archive_name = f"uv-{triple}.tar.gz"
    url = f"https://github.com/astral-sh/uv/releases/latest/download/{archive_name}"
    archive_path = UV_CACHE_DIR / archive_name
    _debug(f"Downloading uv from {url}")
    # Bandit B310: The download is restricted to HTTPS GitHub releases; the
    # generated URL never uses file or custom schemes, so this network fetch is
    # a deliberate and safe dependency bootstrap.
    with urllib.request.urlopen(url) as response, open(archive_path, "wb") as handle:  # nosec B310
        shutil.copyfileobj(response, handle)
    return archive_path


def _resolve_uv_triple() -> str:
    """Return the ``uv`` release triple matching the current system.

    Returns:
        str: Target triple representing the current platform.

    Raises:
        ProbeError: If either the architecture or platform is unsupported.
    """

    system = platform.system().lower()
    machine_raw = platform.machine().lower()
    machine = ARCH_ALIASES.get(machine_raw)
    if machine is None:
        raise ProbeError(f"Unsupported architecture: {platform.machine()}")
    triple = UV_TRIPLES.get((system, machine))
    if triple is None:
        raise ProbeError(f"Unsupported platform: {system}-{machine}")
    return triple


def _extract_uv_binary(archive_path: Path) -> Path:
    """Extract the ``uv`` binary from ``archive_path`` into the cache.

    Args:
        archive_path: Location of the downloaded ``uv`` tarball.

    Returns:
        Path: Final executable location inside ``UV_CACHE_DIR``.

    Raises:
        ProbeError: If the archive is missing a binary or contains unsafe
        paths.
    """

    binary_member: tarfile.TarInfo | None = None
    with tarfile.open(archive_path, "r:gz") as tar:
        for candidate in tar.getmembers():
            if not candidate.name.endswith("/uv"):
                continue
            candidate_path = Path(candidate.name)
            if candidate_path.is_absolute() or PATH_TRAVERSAL_COMPONENT in candidate_path.parts:
                raise ProbeError("Unsafe path in uv archive")
            tar.extract(candidate, path=UV_CACHE_DIR)
            binary_member = candidate
            break
    if binary_member is None:
        raise ProbeError("uv binary not found in archive")

    extracted_path = UV_CACHE_DIR / binary_member.name
    parent = extracted_path.parent
    final_path = UV_CACHE_DIR / "uv"
    extracted_path.rename(final_path)
    if parent != UV_CACHE_DIR and parent.exists():
        shutil.rmtree(parent)
    return final_path


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
