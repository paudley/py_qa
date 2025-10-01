# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for built-in tool registrations."""

from __future__ import annotations

import platform
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Final, Protocol, cast

from ..filesystem.paths import normalize_path
from ..models import RawDiagnostic
from ..severity import Severity
from ..utils.bool_utils import interpret_optional_bool
from .base import ToolContext

__all__ = [
    "CARGO_AVAILABLE",
    "CPANM_AVAILABLE",
    "LUAROCKS_AVAILABLE",
    "LUA_AVAILABLE",
    "_CARGO_AVAILABLE",
    "_CPANM_AVAILABLE",
    "_LUAROCKS_AVAILABLE",
    "_LUA_AVAILABLE",
    "_as_bool",
    "_parse_gofmt_check",
    "_resolve_path",
    "_setting",
    "_settings_list",
    "download_tool_artifact",
]

LUAROCKS_AVAILABLE: Final[bool] = shutil.which("luarocks") is not None
LUA_AVAILABLE: Final[bool] = shutil.which("lua") is not None
CARGO_AVAILABLE: Final[bool] = shutil.which("cargo") is not None
CPANM_AVAILABLE: Final[bool] = shutil.which("cpanm") is not None

_LUAROCKS_AVAILABLE: Final[bool] = LUAROCKS_AVAILABLE
_LUA_AVAILABLE: Final[bool] = LUA_AVAILABLE
_CARGO_AVAILABLE: Final[bool] = CARGO_AVAILABLE
_CPANM_AVAILABLE: Final[bool] = CPANM_AVAILABLE

TAR_GZ_ARCHIVE: Final[str] = "tar.gz"


class _HttpResponse(Protocol):
    """Minimal subset of ``requests.Response`` used by downloads."""

    content: bytes

    def raise_for_status(self) -> None:
        """Raise an exception when the HTTP response indicates failure."""

    def iter_content(self, chunk_size: int = 8192) -> Iterable[bytes]:  # pragma: no cover - protocol default
        """Yield response body chunks; default implementation wraps ``content``."""

        del chunk_size
        return (self.content,)


_RequestsGet = Callable[..., _HttpResponse]


def _load_requests_get() -> _RequestsGet:
    module = import_module("requests")
    get_callable = getattr(module, "get", None)
    if not callable(get_callable):
        msg = "requests.get not available"
        raise RuntimeError(msg)
    return cast(_RequestsGet, get_callable)


_REQUESTS_GET: Final[_RequestsGet] = _load_requests_get()


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
    try:
        normalised = normalize_path(candidate, base_dir=root)
    except (ValueError, OSError):
        return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if normalised.is_absolute():
        return normalised.resolve()
    return (root / normalised).resolve()


def _as_bool(value: object | None) -> bool | None:
    """Interpret arbitrary values as optional booleans."""
    return interpret_optional_bool(value)


@dataclass(frozen=True)
class _DownloadTarget:
    os: tuple[str, ...] | None
    arch: tuple[str, ...] | None
    url: str
    archive_format: str | None
    member: str | None
    filename: str | None
    chmod: bool


def download_tool_artifact(
    spec: Mapping[str, object],
    *,
    version: str | None,
    cache_root: Path,
    context: str,
) -> Path:
    """Download a tool artifact described by *spec* if missing and return its path."""

    tool_name = str(spec.get("name", "tool")).strip() or "tool"
    targets = _parse_download_targets(spec, context=context)
    target = _select_download_target(targets, context=context)

    base_dir = _resolve_cache_directory(
        cache_root,
        spec,
        tool_name=tool_name,
        version=version,
    )
    destination = base_dir / _determine_filename(target)
    if destination.exists():
        return destination

    variables = _DownloadFormatProxy(version=version)
    resolved_url = target.url.format_map(variables)
    timeout = _normalize_timeout(spec.get("timeout", 60), context=context)
    response = _fetch_artifact(resolved_url, timeout=timeout)

    _write_artifact_content(response, target, destination, context=context)
    if target.chmod:
        _make_executable(destination)

    return destination


def _parse_download_targets(
    spec: Mapping[str, object],
    *,
    context: str,
) -> tuple[_DownloadTarget, ...]:
    targets_value = spec.get("targets")
    if not isinstance(targets_value, Sequence) or not targets_value:
        raise RuntimeError(f"{context}: download specification must include targets")
    return tuple(_normalize_download_target(target, context=context) for target in targets_value)


def _resolve_cache_directory(
    cache_root: Path,
    spec: Mapping[str, object],
    *,
    tool_name: str,
    version: str | None,
) -> Path:
    cache_dir = str(spec.get("cacheSubdir", tool_name)).strip() or tool_name
    base_dir = cache_root / cache_dir
    if version:
        base_dir /= version
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _determine_filename(target: _DownloadTarget) -> str:
    return target.filename or target.member or _filename_from_url(target.url)


def _fetch_artifact(url: str, *, timeout: int) -> _HttpResponse:
    response = _REQUESTS_GET(url, timeout=timeout)
    response.raise_for_status()
    return response


def _write_artifact_content(
    response: _HttpResponse,
    target: _DownloadTarget,
    destination: Path,
    *,
    context: str,
) -> None:
    if target.archive_format is None:
        destination.write_bytes(response.content)
        return
    if target.archive_format == TAR_GZ_ARCHIVE:
        _extract_tar_member(response.content, target, destination, context=context)
        return
    raise RuntimeError(f"{context}: unsupported archive format '{target.archive_format}'")


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _normalize_download_target(data: object, *, context: str) -> _DownloadTarget:
    if not isinstance(data, Mapping):
        raise RuntimeError(f"{context}: download target entries must be objects")

    url_value = data.get("url")
    if not isinstance(url_value, str) or not url_value:
        raise RuntimeError(f"{context}: download target requires a non-empty 'url'")

    os_value = data.get("os") or data.get("oses")
    os_list = _normalize_string_sequence(os_value) if os_value is not None else None
    arch_value = data.get("arch") or data.get("architectures")
    arch_list = _normalize_string_sequence(arch_value) if arch_value is not None else None

    archive_value = data.get("archive")
    archive_format = None
    archive_member = None
    if archive_value is not None:
        if not isinstance(archive_value, Mapping):
            raise RuntimeError(f"{context}: archive specification must be an object")
        fmt = archive_value.get("format")
        if not isinstance(fmt, str) or not fmt:
            raise RuntimeError(f"{context}: archive specification requires a 'format'")
        archive_format = fmt.lower()
        member = archive_value.get("member")
        if member is not None and not isinstance(member, str):
            raise RuntimeError(f"{context}: archive member must be a string if provided")
        archive_member = member

    filename_value = data.get("filename")
    if filename_value is not None and not isinstance(filename_value, str):
        raise RuntimeError(f"{context}: filename must be a string when provided")

    chmod_value = data.get("chmod")
    chmod = True if chmod_value is None else bool(chmod_value)

    return _DownloadTarget(
        os=tuple(value.lower() for value in os_list) if os_list else None,
        arch=tuple(value.lower() for value in arch_list) if arch_list else None,
        url=url_value,
        archive_format=archive_format,
        member=archive_member,
        filename=filename_value,
        chmod=chmod,
    )


def _normalize_string_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        result = []
        for item in value:
            if not isinstance(item, str):
                raise RuntimeError("Download target entries must be strings")
            result.append(item)
        return tuple(result)
    raise RuntimeError("Download target sequences must be arrays of strings")


def _select_download_target(targets: Sequence[_DownloadTarget], *, context: str) -> _DownloadTarget:
    system = platform.system().lower()
    machine = _normalize_architecture(platform.machine())

    for target in targets:
        if target.os is not None and system not in target.os:
            continue
        if target.arch is not None and machine not in target.arch:
            continue
        return target

    raise RuntimeError(f"{context}: no download target available for {system}/{machine}")


def _normalize_architecture(machine: str) -> str:
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return "x86_64"
    if normalized in {"aarch64", "arm64"}:
        return "arm64"
    return normalized


def _filename_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


class _DownloadFormatProxy(dict[str, str]):
    """Dictionary proxy used to provide default values for format placeholders."""

    def __init__(self, *, version: str | None) -> None:
        super().__init__()
        if version is not None:
            self["version"] = version

    def __missing__(self, key: str) -> str:
        return ""


def _extract_tar_member(
    content: bytes,
    target: _DownloadTarget,
    destination: Path,
    *,
    context: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "archive.tar.gz"
        tmp_path.write_bytes(content)
        with tarfile.open(tmp_path, "r:gz") as archive:
            extracted = _extract_member_into_directory(
                archive,
                member_name=target.member,
                scratch_dir=Path(tmpdir),
                context=context,
            )

        destination.write_bytes(extracted.read_bytes())


def _normalize_timeout(value: object, *, context: str) -> int:
    """Coerce the timeout value into an integer number of seconds."""

    if isinstance(value, bool):
        raise RuntimeError(f"{context}: timeout must be numeric")
    if isinstance(value, (int, float)):
        if value <= 0:
            raise RuntimeError(f"{context}: timeout must be positive")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.isdigit():
            raise RuntimeError(f"{context}: timeout string must be numeric")
        return int(stripped)
    raise RuntimeError(f"{context}: timeout must be a number")


def _extract_member_into_directory(
    archive: tarfile.TarFile,
    *,
    member_name: str | None,
    scratch_dir: Path,
    context: str,
) -> Path:
    """Extract the requested archive member and return the extracted path."""

    selected_member = _select_tar_member(archive, member_name=member_name, context=context)
    archive.extract(selected_member, path=scratch_dir)
    return scratch_dir / selected_member.name


def _select_tar_member(
    archive: tarfile.TarFile,
    *,
    member_name: str | None,
    context: str,
) -> tarfile.TarInfo:
    """Select a tarfile member either by name or the first regular file."""

    if member_name is not None:
        try:
            return archive.getmember(member_name)
        except KeyError as exc:
            raise RuntimeError(f"{context}: archive missing member '{member_name}'") from exc

    for candidate in archive.getmembers():
        if candidate.isfile():
            return candidate

    raise RuntimeError(f"{context}: archive did not contain any files")


def _parse_gofmt_check(stdout: Sequence[str], _context: ToolContext) -> list[RawDiagnostic]:
    """Convert gofmt --list output into diagnostics describing unformatted files."""
    diagnostics: list[RawDiagnostic] = []
    for line in stdout:
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
