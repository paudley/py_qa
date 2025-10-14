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

from pyqa.core.environment import find_venv_bin
from pyqa.core.environment.tool_env.constants import PROJECT_MARKER_FILENAME
from pyqa.core.runtime.process import CommandOptions, SubprocessExecutionError, run_command

Runner = Callable[[list[str]], CompletedProcess[str]]
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


@dataclass(frozen=True)
class StubRequirement:
    """Runtime package accompanied by its optional typing stubs."""

    runtime: str
    packages: tuple[str, ...]


OPTIONAL_TYPED: tuple[StubRequirement, ...] = (
    StubRequirement("pymysql", ("types-PyMySQL",)),
    StubRequirement("cachetools", ("types-cachetools",)),
    StubRequirement("cffi", ("types-cffi",)),
    StubRequirement("colorama", ("types-colorama",)),
    StubRequirement("python-dateutil", ("types-python-dateutil",)),
    StubRequirement("defusedxml", ("types-defusedxml",)),
    StubRequirement("docutils", ("types-docutils",)),
    StubRequirement("gevent", ("types-gevent",)),
    StubRequirement("greenlet", ("types-greenlet",)),
    StubRequirement("html5lib", ("types-html5lib",)),
    StubRequirement("httplib2", ("types-httplib2",)),
    StubRequirement("jsonschema", ("types-jsonschema",)),
    StubRequirement("libsass", ("types-libsass",)),
    StubRequirement("networkx", ("types-networkx",)),
    StubRequirement("openpyxl", ("types-openpyxl",)),
    StubRequirement("pandas", ("pandas-stubs",)),
    StubRequirement("protobuf", ("types-protobuf",)),
    StubRequirement("psutil", ("types-psutil",)),
    StubRequirement("psycopg2", ("types-psycopg2",)),
    StubRequirement("pyasn1", ("types-pyasn1",)),
    StubRequirement("pyarrow", ("pyarrow-stubs",)),
    StubRequirement("pycurl", ("types-pycurl",)),
    StubRequirement("pygments", ("types-pygments",)),
    StubRequirement("pyopenssl", ("types-pyopenssl",)),
    StubRequirement("pytz", ("types-pytz",)),
    StubRequirement("pywin32", ("types-pywin32",)),
    StubRequirement("pyyaml", ("types-pyyaml",)),
    StubRequirement("requests", ("types-requests",)),
    StubRequirement("scipy", ("scipy-stubs",)),
    StubRequirement("setuptools", ("types-setuptools",)),
    StubRequirement("shapely", ("types-shapely",)),
    StubRequirement("simplejson", ("types-simplejson",)),
    StubRequirement("tabulate", ("types-tabulate",)),
    StubRequirement("tensorflow", ("types-tensorflow",)),
    StubRequirement("tqdm", ("types-tqdm",)),
)

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
    """Install development dependencies and optional typing assets for ``root``.

    Args:
        root: Project directory whose development environment should be provisioned.
        include_optional: When ``True`` install optional runtime-specific stub packages.
        generate_stubs: When ``True`` generate stub skeletons for selected runtimes.
        on_optional_stub: Optional callback invoked for each installed optional stub package.
        on_stub_generation: Optional callback invoked for each generated stub module.

    Returns:
        InstallSummary: Summary describing installed optional stubs, generated modules,
        and the project marker location.
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
    """Execute ``uv`` with ``args`` inside ``project_root``.

    Args:
        args: Command arguments to execute.
        project_root: Directory used as the subprocess working directory.
        check: When ``True`` non-zero exits raise :class:`SubprocessExecutionError`.

    Returns:
        CompletedProcess[str]: Captured subprocess result.
    """

    options = CommandOptions(cwd=project_root, check=check)
    return run_command(args, options=options)


def _installed_packages(project_root: Path) -> set[str]:
    """Return the set of installed package names for ``project_root``.

    Args:
        project_root: Directory containing the project environment.

    Returns:
        set[str]: Lowercase package names known to ``uv`` or an empty set on failure.
    """

    try:
        completed = run_command(
            ["uv", "pip", "list", "--format=json"],
            options=CommandOptions(cwd=project_root, check=True, capture_output=True),
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
    """Install optional stub packages when their runtime dependency is present.

    Args:
        project_root: Project directory where stubs should be installed.
        installed: Lowercase set of already installed runtime packages.
        on_optional_stub: Optional callback invoked when a stub package is added.

    Returns:
        list[str]: Names of stub packages that were installed.
    """

    added: list[str] = []
    for requirement in OPTIONAL_TYPED:
        if requirement.runtime.lower() not in installed:
            continue
        for package in requirement.packages:
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
    """Generate stub modules for installed runtimes not covered by third-party packages.

    Args:
        project_root: Project directory within which stubs are created.
        installed: Lowercase set of installed runtime packages.
        on_stub_generation: Optional callback invoked when stubs are generated.

    Returns:
        list[str]: Module names for which stubs were generated.
    """

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
    """Persist a marker file identifying that the project tools were installed.

    Args:
        project_root: Project directory receiving the marker.

    Returns:
        Path: Path to the written marker file.
    """

    marker = project_root / ".lint-cache" / PROJECT_MARKER_FILENAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"project": True}), encoding="utf-8")
    return marker


def install_with_preferred_manager(
    args: Iterable[str],
    *,
    runner: Runner,
    warn: Warn | None = None,
    project_root: Path | None = None,
) -> CompletedProcess[str]:
    """Install packages using uv/pip preferences.

    Args:
        args: Package specifiers to install.
        runner: Callable used to execute subprocess commands.
        warn: Optional warning callback used when fallbacks trigger.
        project_root: Project directory used to detect uv/virtualenv availability.

    Returns:
        CompletedProcess[str]: Subprocess result from the command that ultimately executed.

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
