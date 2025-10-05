# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for resolving Python version overrides for lint execution."""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, cast

from ..config import ExecutionConfig

_PYTHON_VERSION_PATTERN = re.compile(r"(?P<major>\d{1,2})(?:[._-]?(?P<minor>\d{1,2}))?")
PYPROJECT_TOML_NAME: Final[str] = "pyproject.toml"
PYTHON_VERSION_FILENAME: Final[str] = ".python-version"
PYTHON_VERSION_ENCODING: Final[str] = "utf-8"


def resolve_python_version(
    project_root: Path,
    current: ExecutionConfig,
    cli_specified: bool,
) -> ExecutionConfig:
    """Normalise the Python version for the execution configuration.

    Args:
        project_root: Project root utilised to detect version metadata files.
        current: Execution configuration produced prior to version detection.
        cli_specified: ``True`` when the CLI explicitly provided a version.

    Returns:
        ExecutionConfig: Execution configuration carrying a normalised Python
        version string when available.
    """

    if cli_specified:
        normalized = _normalize_python_version(current.python_version)
        return current.model_copy(update={"python_version": normalized}, deep=True)

    forced = (
        _python_version_from_pyproject(project_root)
        or _python_version_from_python_version_file(project_root)
        or _normalize_python_version(current.python_version)
        or _default_interpreter_python_version()
    )
    return current.model_copy(update={"python_version": forced}, deep=True)


def _default_interpreter_python_version() -> str:
    """Return the interpreter's major.minor Python version string.

    Returns:
        str: Normalised representation of the running interpreter version.
    """

    info = sys.version_info
    return f"{info.major}.{info.minor}"


def _normalize_python_version(value: object | None) -> str | None:
    """Normalise raw Python version tokens into ``major.minor`` strings.

    Args:
        value: Candidate object describing a Python version.

    Returns:
        str | None: Normalised version string when parsing succeeds, otherwise
        ``None``.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    lowered = lowered.removeprefix("python")
    lowered = lowered.removeprefix("py")
    match = _PYTHON_VERSION_PATTERN.search(lowered)
    if not match:
        return None
    major = int(match.group("major"))
    minor_group = match.group("minor")
    minor = int(minor_group) if minor_group is not None and minor_group != "" else 0
    return f"{major}.{minor}"


def _first_normalized_python_version(lines: Iterable[str]) -> str | None:
    """Return the first normalised Python version found in candidate lines.

    Args:
        lines: Iterable of raw text lines containing potential versions.

    Returns:
        str | None: Normalised version string when discovered; otherwise ``None``.
    """

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = _normalize_python_version(stripped)
        if normalized:
            return normalized
    return None


def _python_version_from_python_version_file(root: Path) -> str | None:
    """Resolve the Python version declared in a ``.python-version`` file.

    Args:
        root: Project root used to resolve the version file path.

    Returns:
        str | None: Normalised Python version when the file exists and contains
        a valid declaration; otherwise ``None``.
    """

    candidate = root / PYTHON_VERSION_FILENAME
    if not candidate.is_file():
        return None
    try:
        contents = candidate.read_text(encoding=PYTHON_VERSION_ENCODING)
    except OSError:
        return None
    return _first_normalized_python_version(contents.splitlines())


def _python_version_from_pyproject(root: Path) -> str | None:
    """Resolve the Python version declared in ``pyproject.toml`` metadata.

    Args:
        root: Project root used to resolve the ``pyproject.toml`` path.

    Returns:
        str | None: Normalised Python version when discoverable; otherwise
        ``None``.
    """

    candidate = root / PYPROJECT_TOML_NAME
    if not candidate.is_file():
        return None
    data = _load_pyproject_data(candidate)
    if data is None:
        return None
    return _first_normalized_python_version(_iter_pyproject_python_versions(data))


def _load_pyproject_data(path: Path) -> Mapping[str, object] | None:
    """Load ``pyproject.toml`` as a mapping when possible.

    Args:
        path: Resolved path to the ``pyproject.toml`` file.

    Returns:
        Mapping[str, object] | None: Parsed payload when loadable and
        representable as a mapping; otherwise ``None``.
    """

    try:
        raw = path.read_text(encoding=PYTHON_VERSION_ENCODING)
    except OSError:
        return None
    try:
        parsed: object = tomllib.loads(raw)
    except tomllib.TOMLDecodeError:
        return None
    if isinstance(parsed, dict):
        return cast(Mapping[str, object], parsed)
    return None


def _iter_pyproject_python_versions(data: Mapping[str, object]) -> Iterable[str]:
    """Yield Python version declarations found in ``pyproject.toml``.

    Args:
        data: Parsed ``pyproject`` mapping.

    Yields:
        Iterable of raw version strings discovered in recognised sections.
    """

    project_section = data.get("project")
    if isinstance(project_section, Mapping):
        requires = project_section.get("requires-python")
        if isinstance(requires, str):
            yield requires

    tool_section = data.get("tool")
    if not isinstance(tool_section, Mapping):
        return

    yield from _iter_poetry_python_versions(tool_section)
    yield from _iter_hatch_python_versions(tool_section)


def _iter_poetry_python_versions(tool_section: Mapping[str, object]) -> Iterable[str]:
    """Yield poetry-managed Python version declarations.

    Args:
        tool_section: ``[tool]`` section extracted from ``pyproject``.

    Yields:
        Iterable of poetry-defined Python version requirements.
    """

    poetry_section = tool_section.get("poetry")
    if not isinstance(poetry_section, Mapping):
        return
    dependencies = poetry_section.get("dependencies")
    if not isinstance(dependencies, Mapping):
        return
    poetry_python = dependencies.get("python")
    if isinstance(poetry_python, str):
        yield poetry_python


def _iter_hatch_python_versions(tool_section: Mapping[str, object]) -> Iterable[str]:
    """Yield hatch-managed Python version declarations.

    Args:
        tool_section: ``[tool]`` section extracted from ``pyproject``.

    Yields:
        Iterable of hatch-defined Python version requirements.
    """

    hatch_section = tool_section.get("hatch")
    if not isinstance(hatch_section, Mapping):
        return
    envs = hatch_section.get("envs")
    if not isinstance(envs, Mapping):
        return
    default_env = envs.get("default")
    if not isinstance(default_env, Mapping):
        return
    version = default_env.get("python")
    if isinstance(version, str):
        yield version
