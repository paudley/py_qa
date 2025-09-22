"""Installer helpers that prefer project-local tooling when available."""

from __future__ import annotations

import subprocess  # nosec B404 - subprocess required for controlled installer calls
from pathlib import Path
from shutil import which
from typing import Callable, Iterable

from .environments import find_venv_bin

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]
Warn = Callable[[str], None]


def install_with_preferred_manager(
    args: Iterable[str],
    *,
    runner: Runner,
    warn: Warn | None = None,
    project_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Install packages using uv/pip preferences.

    The resolution order matches the legacy script:
    1. ``uv add --dev`` when ``pyproject.toml`` is present.
    2. ``pip`` inside the project's virtualenv if one exists.
    3. ``uv pip install`` (and fallback to ``uv run -m pip``).
    4. System ``pip3`` or ``pip``.
    """

    warn = warn or (lambda message: None)
    project_root = project_root or Path.cwd()
    args_list = list(args)

    venv_bin = find_venv_bin(project_root)

    if (project_root / "pyproject.toml").is_file() and which("uv"):
        cp = runner(["uv", "add", "-q", "--dev", *args_list])
        if cp.returncode == 0:
            return cp
        warn("uv add --dev failed; falling back to pip install methods")

    if venv_bin and (venv_bin / "pip").exists():
        return runner([str(venv_bin / "pip"), "install", "-U", *args_list])

    if which("uv"):
        cp = runner(["uv", "pip", "install", "-U", *args_list])
        if cp.returncode != 0:
            warn("uv pip install failed; trying 'uv run -m pip'")
            return runner(["uv", "run", "-m", "pip", "install", "-U", *args_list])
        return cp

    pip_exe = which("pip3") or which("pip")
    if pip_exe:
        return runner([pip_exe, "install", "-U", *args_list])

    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="pip not found"
    )
