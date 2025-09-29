# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helper utilities retained for catalog-driven command strategies."""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path

from .base import ToolContext

_BASE_PYLINT_PLUGINS: tuple[str, ...] = (
    "pylint.extensions.bad_builtin",
    "pylint.extensions.broad_try_clause",
    "pylint.extensions.check_elif",
    "pylint.extensions.code_style",
    "pylint.extensions.comparison_placement",
    "pylint.extensions.confusing_elif",
    "pylint.extensions.consider_ternary_expression",
    "pylint.extensions.dict_init_mutate",
    "pylint.extensions.docparams",
    "pylint.extensions.docstyle",
    "pylint.extensions.empty_comment",
    "pylint.extensions.eq_without_hash",
    "pylint.extensions.for_any_all",
    "pylint.extensions.magic_value",
    "pylint.extensions.mccabe",
    "pylint.extensions.overlapping_exceptions",
    "pylint.extensions.redefined_loop_name",
    "pylint.extensions.redefined_variable_type",
    "pylint.extensions.set_membership",
    "pylint.extensions.typing",
    "pylint.extensions.while_used",
    "pylint_htmf",
    "pylint_pydantic",
)

_OPTIONAL_PYLINT_PLUGINS: dict[str, str] = {
    "django": "pylint_django",
    "celery": "pylint_celery",
    "flask": "pylint_flask",
    "pytest": "pylint_pytest",
    "sqlalchemy": "pylint_sqlalchemy",
    "odoo": "pylint_odoo",
    "quotes": "pylint_quotes",
}


def _python_target_version(ctx: ToolContext) -> str:
    """Return the configured Python version or fall back to the interpreter."""
    version = getattr(ctx.cfg.execution, "python_version", None)
    if version:
        return str(version)
    info = sys.version_info
    return f"{info.major}.{info.minor}"


def _python_version_components(version: str) -> tuple[int, int]:
    """Extract major/minor components from a Python version string."""
    match = re.search(r"(\d{1,2})(?:[._-]?(\d{1,2}))?", version)
    if not match:
        return sys.version_info.major, sys.version_info.minor
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else 0
    return major, minor


def _python_version_tag(version: str) -> str:
    """Convert *version* into ruff/black style ``pyXY`` tag."""
    major, minor = _python_version_components(version)
    return f"py{major}{minor}"


def _python_version_number(version: str) -> str:
    """Convert *version* into isort style ``XY`` number without separator."""
    major, minor = _python_version_components(version)
    return f"{major}{minor}"


def _pyupgrade_flag_from_version(version: str) -> str:
    """Map a Python version specifier to pyupgrade's ``--pyXY-plus`` flag."""
    normalized = version.lower().lstrip("py").rstrip("+")
    if not normalized:
        normalized = f"{sys.version_info.major}.{sys.version_info.minor}"
    parts = normalized.split(".")
    if len(parts) > 1:
        major, minor = parts[0], parts[1]
    else:
        major = parts[0][:1] if parts[0] else str(sys.version_info.major)
        minor = parts[0][1:] if len(parts[0]) > 1 else "0"
        if not minor:
            minor = "0"
    return f"--py{major}{minor}-plus"


def _discover_pylint_plugins(root: Path) -> tuple[str, ...]:
    """Return default pylint plugins, discovering optional extras when present."""
    discovered: set[str] = set()

    def _loadable(module: str) -> bool:
        try:
            spec = importlib.util.find_spec(module)
            if spec is None:
                return False
            mod = importlib.import_module(module)
            return hasattr(mod, "register")
        except Exception:
            return False

    for plugin in _BASE_PYLINT_PLUGINS:
        if _loadable(plugin):
            discovered.add(plugin)

    for requirement, plugin in _OPTIONAL_PYLINT_PLUGINS.items():
        if _loadable(requirement) and _loadable(plugin):
            discovered.add(plugin)

    if (root / ".venv").is_dir() and _loadable("pylint_venv"):
        discovered.add("pylint_venv")

    return tuple(sorted(discovered))


__all__ = [
    "_discover_pylint_plugins",
    "_python_target_version",
    "_python_version_number",
    "_python_version_tag",
    "_pyupgrade_flag_from_version",
]
