# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for built-in tool registrations."""

from __future__ import annotations

import platform
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Final, Protocol, cast

from ..models import RawDiagnostic
from ..severity import Severity
from .base import ToolContext

__all__ = [
    "ACTIONLINT_VERSION_DEFAULT",
    "CARGO_AVAILABLE",
    "CPANM_AVAILABLE",
    "HADOLINT_VERSION_DEFAULT",
    "LUAROCKS_AVAILABLE",
    "LUA_AVAILABLE",
    "_CARGO_AVAILABLE",
    "_CPANM_AVAILABLE",
    "_LUAROCKS_AVAILABLE",
    "_LUA_AVAILABLE",
    "_as_bool",
    "_ensure_actionlint",
    "_ensure_hadolint",
    "_ensure_lualint",
    "_parse_gofmt_check",
    "_resolve_path",
    "_setting",
    "_settings_list",
    "ensure_actionlint",
    "ensure_hadolint",
    "ensure_lualint",
]

ACTIONLINT_VERSION_DEFAULT: Final[str] = "1.7.1"
HADOLINT_VERSION_DEFAULT: Final[str] = "2.12.0"
LUAROCKS_AVAILABLE: Final[bool] = shutil.which("luarocks") is not None
LUA_AVAILABLE: Final[bool] = shutil.which("lua") is not None
CARGO_AVAILABLE: Final[bool] = shutil.which("cargo") is not None
CPANM_AVAILABLE: Final[bool] = shutil.which("cpanm") is not None

_LUAROCKS_AVAILABLE: Final[bool] = LUAROCKS_AVAILABLE
_LUA_AVAILABLE: Final[bool] = LUA_AVAILABLE
_CARGO_AVAILABLE: Final[bool] = CARGO_AVAILABLE
_CPANM_AVAILABLE: Final[bool] = CPANM_AVAILABLE


class _HttpResponse(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class _RequestsClient(Protocol):
    def get(self, url: str, **kwargs: object) -> _HttpResponse: ...


def _load_requests() -> _RequestsClient:
    module = import_module("requests")
    if not hasattr(module, "get"):
        msg = "requests.get not available"
        raise RuntimeError(msg)
    return cast("_RequestsClient", module)


_REQUESTS: Final[_RequestsClient] = _load_requests()


def _setting(settings: Mapping[str, object], *names: str) -> object | None:
    """Return the first configured value from *names* within *settings*."""
    for name in names:
        if name in settings:
            return settings[name]
        alt = name.replace("-", "_")
        if alt in settings:
            return settings[alt]
    return None


def _settings_list(value: object) -> list[str]:
    """Coerce a setting value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    return [str(value)]


def _resolve_path(root: Path, value: object) -> Path:
    """Return an absolute path for *value* anchored at *root* when needed."""
    candidate = Path(str(value)).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _as_bool(value: object | None) -> bool | None:
    """Interpret arbitrary values as optional booleans."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _ensure_actionlint(version: str, cache_root: Path) -> Path:
    """Download the requested actionlint release if needed and return its binary path."""
    base_dir = cache_root / "actionlint" / version
    binary = base_dir / "actionlint"
    if binary.exists():
        return binary

    base_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            platform_tag = "linux_amd64"
        elif machine in {"aarch64", "arm64"}:
            platform_tag = "linux_arm64"
        else:
            msg = f"Unsupported Linux architecture '{machine}' for actionlint"
            raise RuntimeError(msg)
    elif system == "darwin":
        if machine in {"x86_64", "amd64"}:
            platform_tag = "darwin_amd64"
        elif machine in {"arm64", "aarch64"}:
            platform_tag = "darwin_arm64"
        else:
            msg = f"Unsupported macOS architecture '{machine}' for actionlint"
            raise RuntimeError(msg)
    else:
        msg = f"actionlint is not supported on platform '{system}'"
        raise RuntimeError(msg)

    filename = f"actionlint_{version}_{platform_tag}.tar.gz"
    url = f"https://github.com/rhysd/actionlint/releases/download/v{version}/{filename}"

    response = _REQUESTS.get(url, timeout=30)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(response.content)
        tmp.flush()
        with tarfile.open(tmp.name, "r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith("actionlint"):
                    archive.extract(member, path=base_dir)
                    extracted = base_dir / member.name
                    extracted.chmod(
                        extracted.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
                    )
                    if extracted != binary:
                        extracted.rename(binary)
                    break
            else:
                raise RuntimeError("Failed to locate actionlint binary in archive")

    return binary


def _ensure_hadolint(version: str, cache_root: Path) -> Path:
    """Download the requested hadolint release when missing."""
    base_dir = cache_root / "hadolint" / version
    binary = base_dir / "hadolint"
    if binary.exists():
        return binary

    base_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            asset = "hadolint-Linux-x86_64"
        elif machine in {"aarch64", "arm64"}:
            asset = "hadolint-Linux-arm64"
        else:
            msg = f"Unsupported Linux architecture '{machine}' for hadolint"
            raise RuntimeError(msg)
    elif system == "darwin":
        if machine in {"x86_64", "amd64"}:
            asset = "hadolint-Darwin-x86_64"
        elif machine in {"arm64", "aarch64"}:
            asset = "hadolint-Darwin-arm64"
        else:
            msg = f"Unsupported macOS architecture '{machine}' for hadolint"
            raise RuntimeError(msg)
    else:
        msg = f"hadolint is not supported on platform '{system}'"
        raise RuntimeError(msg)

    url = f"https://github.com/hadolint/hadolint/releases/download/v{version}/{asset}"
    response = _REQUESTS.get(url, timeout=60)
    response.raise_for_status()
    binary.write_bytes(response.content)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return binary


def _ensure_lualint(cache_root: Path) -> Path:
    """Download the standalone lualint script if missing."""
    base_dir = cache_root / "lualint"
    script = base_dir / "lualint.lua"
    if script.exists():
        return script

    base_dir.mkdir(parents=True, exist_ok=True)

    url = "https://raw.githubusercontent.com/philips/lualint/master/lualint"
    response = _REQUESTS.get(url, timeout=30)
    response.raise_for_status()
    script.write_bytes(response.content)
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def ensure_actionlint(version: str, cache_root: Path) -> Path:
    """Public helper for installing actionlint."""
    return _ensure_actionlint(version, cache_root)


def ensure_hadolint(version: str, cache_root: Path) -> Path:
    """Public helper for installing hadolint."""
    return _ensure_hadolint(version, cache_root)


def ensure_lualint(cache_root: Path) -> Path:
    """Public helper for writing the lualint shim."""
    return _ensure_lualint(cache_root)


def _parse_gofmt_check(stdout: str, _context: ToolContext) -> list[RawDiagnostic]:
    """Convert gofmt --list output into diagnostics describing unformatted files."""
    diagnostics: list[RawDiagnostic] = []
    for line in stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        diagnostics.append(
            RawDiagnostic(
                file=path,
                line=None,
                column=None,
                severity=Severity.WARNING,
                message="File requires gofmt formatting",
                code="gofmt",
                tool="gofmt",
            ),
        )
    return diagnostics
