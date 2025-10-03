# SPDX-License-Identifier: MIT
"""Shared launcher utilities for command-line wrappers."""

from __future__ import annotations

import ast
import io
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

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SRC_DIR: Final[Path] = PROJECT_ROOT / "src"
CACHE_DIR: Final[Path] = PROJECT_ROOT / ".lint-cache"
UV_CACHE_DIR: Final[Path] = CACHE_DIR / "uv"
PYTHON_OVERRIDE_ENV: Final[str] = "PYQA_PYTHON"
UV_COMMAND_ENV: Final[str] = "PYQA_UV"
VERBOSE_ENV: Final[str] = "PYQA_WRAPPER_VERBOSE"
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

    """

    args = list(sys.argv[1:] if argv is None else argv)
    interpreter = _select_interpreter()
    env = _build_env(interpreter)

    if _probe_interpreter(interpreter, env):
        _run_with_python(interpreter, command, args, env)
        return

    uv_path = _ensure_uv()
    _run_with_uv(uv_path, command, args)


def _debug(message: str) -> None:
    """Emit a debug message when wrapper verbosity is enabled.

    Args:
        message: Human-readable details to emit.

    Returns:
        None

    """

    if os.environ.get(VERBOSE_ENV):
        print(message, file=sys.stderr)


def _select_interpreter() -> Path:
    """Return the interpreter that should execute the CLI.

    Returns:
        Path: Absolute path to the interpreter binary that should run the
        command.

    """

    override = os.environ.get(PYTHON_OVERRIDE_ENV)
    if override:
        path = Path(shutil.which(override) or override).expanduser()
        if not path.exists():
            print(f"PYQA_PYTHON interpreter not found: {path}", file=sys.stderr)
            sys.exit(1)
        _debug(f"Using PYQA_PYTHON interpreter: {path}")
        return path

    repo_python = (PROJECT_ROOT / ".venv" / "bin" / "python").expanduser()
    if repo_python.exists():
        _debug(f"Using repository virtualenv interpreter: {repo_python}")
        return repo_python

    current = Path(sys.executable).expanduser()
    _debug(f"Using current interpreter: {current}")
    return current


def _build_env(python_path: Path) -> dict[str, str]:
    """Return an environment mapping with repository ``src`` on the path.

    Args:
        python_path: Interpreter that will execute the CLI.

    Returns:
        dict[str, str]: Environment variables for subprocess execution that
        prefer the repository sources and remember the interpreter choice.

    """

    env = os.environ.copy()
    env["PYQA_SELECTED_PYTHON"] = str(python_path)

    existing = env.get("PYTHONPATH", "")
    src_path = str(SRC_DIR)
    parts = [segment for segment in existing.split(os.pathsep) if segment]
    if src_path not in parts:
        env["PYTHONPATH"] = os.pathsep.join([src_path, *parts]) if parts else src_path

    python_dir = str(python_path.parent)
    path_parts = [segment for segment in env.get("PATH", "").split(os.pathsep) if segment]
    if python_dir and python_dir not in path_parts:
        env["PATH"] = os.pathsep.join([python_dir, *path_parts]) if path_parts else python_dir

    return env


def _probe_interpreter(python_path: Path, env: dict[str, str]) -> bool:
    """Return ``True`` when ``python_path`` can import pyqa from ``src``.

    Args:
        python_path: Interpreter under evaluation.
        env: Environment mapping used during the probe execution.

    Returns:
        bool: ``True`` when the interpreter can import pyqa directly from the
        repository sources, otherwise ``False``.

    """

    if not _is_python_version_compatible(python_path):
        _debug("Interpreter version too old; will use uv fallback.")
        return False

    try:
        status = _run_probe_script(python_path, env)
    except ProbeError as exc:  # pragma: no cover - defensive guard
        _debug(f"Probe failed: {exc}")
        return False

    _debug(f"Probe result: {status.value}")
    return status is ProbeStatus.OK


def _run_probe_script(python_path: Path, env: dict[str, str]) -> ProbeStatus:
    """Execute the probe script and return its :class:`ProbeStatus`.

    Args:
        python_path: Interpreter to execute the probe.
        env: Environment mapping used when running the script.

    Returns:
        ProbeStatus: Outcome reported by the probe script.

    Raises:
        ProbeError: If the subprocess exits with an error or emits an unknown
            payload.

    """

    try:
        result = subprocess.run(
            [str(python_path), "-c", PROBE_SCRIPT],
            env=env,
            check=True,
            capture_output=True,
        )
    except subprocess.SubprocessError as exc:  # pragma: no cover - subprocess failure
        raise ProbeError(str(exc)) from exc

    output = result.stdout.decode().strip() or ProbeStatus.MISSING.value
    try:
        return ProbeStatus(output)
    except ValueError as exc:  # pragma: no cover - unexpected payload
        raise ProbeError(f"Unexpected probe output: {output}") from exc


def _is_python_version_compatible(python_path: Path) -> bool:
    """Return ``True`` when the interpreter meets the minimum version.

    Args:
        python_path: Interpreter under consideration.

    Returns:
        bool: ``True`` when the interpreter satisfies :data:`MIN_PYTHON`.

    """

    try:
        version_tuple = _read_version_tuple(python_path)
    except (ValueError, subprocess.SubprocessError) as exc:
        _debug(f"Version probe failed: {exc}")
        return False

    if version_tuple < MIN_PYTHON:
        _debug(f"Interpreter {python_path} version {version_tuple} < {MIN_PYTHON}.")
        return False
    return True


def _read_version_tuple(python_path: Path) -> tuple[int, int]:
    """Return the interpreter's ``(major, minor)`` version tuple.

    Args:
        python_path: Interpreter whose version should be reported.

    Returns:
        tuple[int, int]: The ``(major, minor)`` portion of ``sys.version_info``.

    Raises:
        ValueError: If the interpreter produced an unexpected payload.

    """

    result = subprocess.run(
        [str(python_path), "-c", "import sys; print(sys.version_info[:2])"],
        check=True,
        capture_output=True,
    )
    raw = result.stdout.decode().strip()
    parsed = ast.literal_eval(raw)
    if (
        not isinstance(parsed, tuple)
        or len(parsed) != VERSION_COMPONENTS
        or not all(isinstance(item, int) for item in parsed)
    ):
        raise ValueError(f"Unexpected version payload: {raw}")
    return parsed  # type: ignore[return-value]


def _run_with_python(
    executable: Path,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> None:
    """Execute the CLI using the supplied interpreter.

    Args:
        executable: Interpreter binary to invoke.
        command: Typer sub-command to execute.
        args: Remaining command-line arguments.
        env: Environment mapping used when spawning the subprocess.

    """

    _debug(f"Running with local interpreter: {executable}")
    code = _build_cli_invocation_code([command, *args])
    result = subprocess.run([str(executable), "-c", code], env=env, check=False)
    sys.exit(result.returncode)


def _run_with_uv(uv_path: Path, command: str, args: list[str]) -> None:
    """Execute the CLI via ``uv run`` when probing fails.

    Args:
        uv_path: Path to the ``uv`` executable.
        command: Typer sub-command to execute.
        args: Remaining command-line arguments.

    """

    _debug(f"Running with uv: {uv_path}")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    code = _build_cli_invocation_code([command, *args])
    cmd = [
        str(uv_path),
        "--project",
        str(PROJECT_ROOT),
        "run",
        "python",
        "-c",
        code,
    ]
    result = subprocess.run(cmd, env=env, check=False)
    sys.exit(result.returncode)


def _build_cli_invocation_code(argv_payload: Iterable[str]) -> str:
    """Return a Python snippet that executes the Typer command directly.

    Args:
        argv_payload: Arguments to forward to the Typer command.

    Returns:
        str: Python source code that loads the Typer application and executes
        the requested command.

    """

    argv_list = list(argv_payload)
    return (
        "import sys\n"
        "from typer.main import get_command\n"
        "from pyqa.cli.app import app as _app\n"
        f"argv = {argv_list!r}\n"
        "command = get_command(_app)\n"
        f"command.main(args=argv, prog_name={PROG_NAME!r})\n"
    )


def _ensure_uv() -> Path:
    """Return a usable ``uv`` executable, downloading it when absent.

    Returns:
        Path: Location of the ``uv`` executable to use.

    """

    override = os.environ.get(UV_COMMAND_ENV)
    if override:
        path = Path(shutil.which(override) or override).expanduser()
        if not path.exists():
            print(f"PYQA_UV executable not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    found = shutil.which("uv")
    if found:
        return Path(found)

    return _download_uv_binary()


def _download_uv_binary() -> Path:
    """Download the ``uv`` binary into the wrapper cache.

    Returns:
        Path: Location of the cached ``uv`` executable.

    """

    triple = _detect_uv_triple()
    target_dir = UV_CACHE_DIR / triple
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "uv"
    if target.exists():
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
        return target

    url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{triple}.tar.gz"
    _debug(f"Downloading uv from {url}")
    archive = _download_uv_archive(url)
    _extract_uv_archive(archive, target_dir)
    _promote_uv_binary(target_dir, target)
    return target


def _download_uv_archive(url: str) -> bytes:
    """Return the raw bytes of the ``uv`` archive located at ``url``.

    Args:
        url: Remote location of the ``uv`` tarball.

    Returns:
        bytes: Archive contents suitable for extraction.

    """

    try:
        response = urllib.request.urlopen(url)
    except OSError as exc:  # pragma: no cover - network failure
        print(f"Failed to download uv: {exc}", file=sys.stderr)
        sys.exit(1)
    with response:
        return response.read()


def _extract_uv_archive(archive: bytes, target_dir: Path) -> None:
    """Extract ``archive`` safely into ``target_dir``.

    Args:
        archive: Raw archive bytes to extract.
        target_dir: Destination directory for the extracted binary.

    Raises:
        RuntimeError: If the archive attempts to escape ``target_dir``.

    """

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            member_path = target_dir / member.name
            if not _is_within(target_dir, member_path):
                raise RuntimeError(f"Refusing to extract uv outside cache: {member.name}")
        tar.extractall(target_dir)


def _promote_uv_binary(source_dir: Path, target: Path) -> None:
    """Promote the ``uv`` binary within ``source_dir`` to ``target``.

    Args:
        source_dir: Directory containing extracted files.
        target: Destination path for the executable.

    """

    for candidate in source_dir.rglob("uv"):
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | stat.S_IEXEC)
            if candidate == target:
                return
            try:
                os.replace(candidate, target)
            except OSError:
                target.write_bytes(candidate.read_bytes())
            return

    print("Downloaded uv but could not locate the binary.", file=sys.stderr)
    sys.exit(1)


def _detect_uv_triple() -> str:
    """Return the platform triple used to download ``uv``.

    Returns:
        str: Platform triple matching the host system.

    """

    system = platform.system().lower()
    machine = ARCH_ALIASES.get(platform.machine().lower(), platform.machine().lower())
    triple = UV_TRIPLES.get((system, machine))
    if triple is None:
        print(f"Unsupported platform for uv auto-download: {system}/{machine}", file=sys.stderr)
        sys.exit(1)
    return triple


def _is_within(root: Path, candidate: Path) -> bool:
    """Return ``True`` when ``candidate`` is located within ``root``.

    Args:
        root: Directory that should contain ``candidate``.
        candidate: Path that must reside within ``root``.

    Returns:
        bool: ``True`` when ``candidate`` is inside ``root``.

    """

    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
