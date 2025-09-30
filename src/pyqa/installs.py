# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Installer helpers that prefer project-local tooling when available."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from subprocess import CompletedProcess
from types import SimpleNamespace
from typing import Any

from .environments import find_venv_bin
from .process_utils import SubprocessExecutionError, run_command
from .tool_env import PROJECT_MARKER

Runner = Callable[[list[str]], Any]
Warn = Callable[[str], None]


DEV_DEPENDENCIES: tuple[str, ...] = (
    "autopep8",
    "bandit[baseline,toml,sarif]",
    "black",
    "bs4",
    "isort",
    "markdown",
    "mypy-extensions",
    "mypy",
    "pycodestyle",
    "pyflakes",
    "pylint-htmf",
    "pylint-plugin-utils",
    "pylint-pydantic",
    "pylint",
    "pyright",
    "pyupgrade",
    "ruff",
    "twine",
    "types-aiofiles",
    "types-markdown",
    "types-regex",
    "types-decorator",
    "types-pexpect",
    "typing-extensions",
    "typing-inspection",
    "uv",
    "vulture",
)

OPTIONAL_TYPED: dict[str, tuple[str, ...]] = {
    "pymysql": ("types-PyMySQL",),
    "cachetools": ("types-cachetools",),
    "cffi": ("types-cffi",),
    "colorama": ("types-colorama",),
    "python-dateutil": ("types-python-dateutil",),
    "defusedxml": ("types-defusedxml",),
    "docutils": ("types-docutils",),
    "gevent": ("types-gevent",),
    "greenlet": ("types-greenlet",),
    "html5lib": ("types-html5lib",),
    "httplib2": ("types-httplib2",),
    "jsonschema": ("types-jsonschema",),
    "libsass": ("types-libsass",),
    "networkx": ("types-networkx",),
    "openpyxl": ("types-openpyxl",),
    "pandas": ("pandas-stubs",),
    "protobuf": ("types-protobuf",),
    "psutil": ("types-psutil",),
    "psycopg2": ("types-psycopg2",),
    "pyasn1": ("types-pyasn1",),
    "pyarrow": ("pyarrow-stubs",),
    "pycurl": ("types-pycurl",),
    "pygments": ("types-pygments",),
    "pyopenssl": ("types-pyopenssl",),
    "pytz": ("types-pytz",),
    "pywin32": ("types-pywin32",),
    "pyyaml": ("types-pyyaml",),
    "requests": ("types-requests",),
    "scipy": ("scipy-stubs",),
    "setuptools": ("types-setuptools",),
    "shapely": ("types-shapely",),
    "simplejson": ("types-simplejson",),
    "tabulate": ("types-tabulate",),
    "tensorflow": ("types-tensorflow",),
    "tqdm": ("types-tqdm",),
}

STUB_GENERATION: dict[str, tuple[str, ...]] = {
    "chromadb": ("chromadb",),
    "geopandas": ("geopandas",),
    "polars": ("polars",),
    "pyarrow": ("pyarrow", "pyarrow.parquet"),
    "pyreadstat": ("pyreadstat",),
    "scikit-learn": ("sklearn",),
    "tolerantjson": ("tolerantjson",),
}


@dataclass(slots=True)
class InstallSummary:
    """Aggregated details about an installation run."""

    optional_stub_packages: tuple[str, ...]
    generated_stub_modules: tuple[str, ...]
    marker_path: Path


def install_dev_environment(
    root: Path,
    *,
    include_optional: bool = True,
    generate_stubs: bool = True,
    on_optional_stub: Callable[[str], None] | None = None,
    on_stub_generation: Callable[[str], None] | None = None,
) -> InstallSummary:
    """Install development dependencies and optional typing assets for *root*.

    The command mirrors the legacy shell behaviour: install core dev dependencies
    via ``uv``, add optional stub packages when their runtime dependency is
    present, generate local stub skeletons for select packages, and stamp the
    tool cache with a project marker.
    """
    project_root = root.resolve()
    _run_uv(
        ["uv", "add", "-q", "--dev", *DEV_DEPENDENCIES],
        project_root,
        check=True,
    )

    installed: set[str] | None = None
    optional_added: list[str] = []
    if include_optional:
        installed = _installed_packages(project_root)
        optional_added = _install_optional_stubs(
            project_root,
            installed,
            on_optional_stub=on_optional_stub,
        )

    generated_modules: list[str] = []
    if generate_stubs:
        if installed is None:
            installed = _installed_packages(project_root)
        generated_modules = _generate_runtime_stubs(
            project_root,
            installed,
            on_stub_generation=on_stub_generation,
        )

    marker = _write_project_marker(project_root)
    return InstallSummary(
        optional_stub_packages=tuple(optional_added),
        generated_stub_modules=tuple(generated_modules),
        marker_path=marker,
    )


def _run_uv(args: Sequence[str], project_root: Path, *, check: bool) -> CompletedProcess[str]:
    return run_command(args, cwd=project_root, check=check)


def _installed_packages(project_root: Path) -> set[str]:
    try:
        completed = run_command(
            ["uv", "pip", "list", "--format=json"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, SubprocessExecutionError):
        return set()

    try:
        data = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return set()

    packages: set[str] = set()
    for entry in data:
        if isinstance(entry, Mapping) and entry.get("name"):
            packages.add(str(entry["name"]).lower())
    return packages


def _install_optional_stubs(
    project_root: Path,
    installed: set[str],
    *,
    on_optional_stub: Callable[[str], None] | None,
) -> list[str]:
    added: list[str] = []
    for runtime, extras in OPTIONAL_TYPED.items():
        if runtime.lower() not in installed:
            continue
        for package in extras:
            if on_optional_stub is not None:
                on_optional_stub(package)
            _run_uv(
                ["uv", "add", "-q", "--dev", package],
                project_root,
                check=False,
            )
            added.append(package)
    return added


def _generate_runtime_stubs(
    project_root: Path,
    installed: set[str],
    *,
    on_stub_generation: Callable[[str], None] | None,
) -> list[str]:
    stubs_root = project_root / "stubs"
    stubs_root.mkdir(exist_ok=True)

    generated: list[str] = []
    for runtime, modules in STUB_GENERATION.items():
        if runtime.lower() not in installed:
            continue
        for module in modules:
            target = stubs_root / module
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if on_stub_generation is not None:
                on_stub_generation(module)
            _run_uv(
                ["uv", "run", "stubgen", "--package", module, "--output", str(target)],
                project_root,
                check=False,
            )
            generated.append(module)
    return generated


def _write_project_marker(project_root: Path) -> Path:
    marker = project_root / ".lint-cache" / PROJECT_MARKER.name
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"project": True}), encoding="utf-8")
    return marker


def install_with_preferred_manager(
    args: Iterable[str],
    *,
    runner: Runner,
    warn: Warn | None = None,
    project_root: Path | None = None,
) -> Any:
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
            warn("uv pip install failed")
        return cp

    pip_exe = which("pip3") or which("pip")
    if pip_exe:
        return runner([pip_exe, "install", "-U", *args_list])

    return SimpleNamespace(
        args=[],
        returncode=1,
        stdout="",
        stderr="pip not found",
    )
