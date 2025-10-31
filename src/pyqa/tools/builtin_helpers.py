# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for built-in tool registrations."""

from __future__ import annotations

import importlib
import platform
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

from pyqa.cache.in_memory import memoize
from pyqa.core.severity import Severity
from pyqa.interfaces.tools import ToolContext

from ..config.types import ConfigValue
from ..core.models import RawDiagnostic
from ..filesystem.paths import normalize_path
from ..utils.bool_utils import interpret_optional_bool

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
        """Yield response body chunks; default implementation wraps ``content``.

        Args:
            chunk_size: Preferred chunk size in bytes.

        Returns:
            Iterable[bytes]: Tuple containing a single chunk with the full body.
        """

        del chunk_size
        return (self.content,)


class _RequestsGet(Protocol):
    """Callable compatible with ``requests.get`` for the subset of parameters we use."""

    def __call__(
        self,
        url: str | bytes,
        params: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
        *,
        timeout: float | tuple[float | None, float | None] | None = None,
    ) -> _HttpResponse:
        """Return an HTTP response for ``url``.

        Args:
            url: Request URL or fully qualified endpoint string.
            params: Optional query parameters encoded with the request.
            timeout: Optional timeout in seconds or connect/read tuple.

        Returns:
            _HttpResponse: HTTP response wrapper provided by ``requests``.
        """

        raise RuntimeError("_RequestsGet protocol requires a concrete implementation")

    def __repr__(self) -> str:
        """Return a debugging representation for the GET callable.

        Returns:
            str: Qualified name identifying the callable.
        """

        return f"RequestsGet({self.__class__.__qualname__})"


@memoize(maxsize=1)
def _load_requests_get() -> _RequestsGet:
    """Return the cached ``requests.get`` callable.

    Returns:
        _RequestsGet: Requests GET function used for downloads.

    Raises:
        RuntimeError: If the ``requests`` package is not available.
    """

    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError as exc:
        raise RuntimeError("requests package is required to download tool artifacts") from exc
    get_callable: _RequestsGet = cast(_RequestsGet, requests.get)
    return get_callable


SettingsMapping = Mapping[str, ConfigValue]


def _setting(settings: SettingsMapping, *names: str) -> ConfigValue | None:
    """Return the first configured value from ``names`` within ``settings``.

    Args:
        settings: Mapping of configuration keys to values.
        *names: Candidate option names to evaluate in order.

    Returns:
        ConfigValue | None: Matching configuration value when present, otherwise ``None``.
    """
    for name in names:
        if name in settings:
            return settings[name]
        alt = name.replace("-", "_")
        if alt in settings:
            return settings[alt]
    return None


def _settings_list(value: ConfigValue | None) -> list[str]:
    """Coerce a setting value into a list of strings.

    Args:
        value: Arbitrary configuration value.

    Returns:
        list[str]: Normalised list of string values.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    return [str(value)]


def _resolve_path(root: Path, value: ConfigValue) -> Path:
    """Return an absolute path for ``value`` anchored at ``root`` when needed.

    Args:
        root: Base directory used to resolve relative paths.
        value: Path-like configuration value supplied by the user.

    Returns:
        Path: Resolved absolute path.
    """
    candidate = Path(str(value)).expanduser()
    try:
        normalised = normalize_path(candidate, base_dir=root)
    except (ValueError, OSError):
        return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if normalised.is_absolute():
        return normalised.resolve()
    return (root / normalised).resolve()


def _as_bool(value: ConfigValue | None) -> bool | None:
    """Interpret arbitrary configuration values as optional booleans.

    Args:
        value: Configuration value to interpret.

    Returns:
        bool | None: Parsed boolean value or ``None`` when unset.

    Raises:
        TypeError: If ``value`` cannot be interpreted as a boolean.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return interpret_optional_bool(value)
    raise TypeError("boolean settings must be bool, string, or numeric values")


@dataclass(frozen=True)
class _DownloadTarget:
    """Describe a download target resolved from catalog metadata."""

    os: tuple[str, ...] | None
    arch: tuple[str, ...] | None
    url: str
    archive_format: str | None
    member: str | None
    filename: str | None
    chmod: bool


def download_tool_artifact(
    spec: Mapping[str, ConfigValue],
    *,
    version: str | None,
    cache_root: Path,
    context: str,
) -> Path:
    """Download a tool artifact when missing and return its cache path.

    Args:
        spec: Mapping describing the download targets and metadata.
        version: Optional version string used for cache naming.
        cache_root: Cache directory where artifacts should reside.
        context: Human-readable context used for error reporting.

    Returns:
        Path: Filesystem path to the downloaded (or existing) artifact.
    """

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
    spec: Mapping[str, ConfigValue],
    *,
    context: str,
) -> tuple[_DownloadTarget, ...]:
    """Return normalised download targets extracted from ``spec``.

    Args:
        spec: Download specification containing target descriptors.
        context: Human-readable context used for error reporting.

    Returns:
        tuple[_DownloadTarget, ...]: Tuple of validated download targets.
    """

    targets_value = spec.get("targets")
    if not isinstance(targets_value, Sequence) or not targets_value:
        raise RuntimeError(f"{context}: download specification must include targets")
    normalized_targets: list[_DownloadTarget] = []
    for target in targets_value:
        if not isinstance(target, Mapping):
            raise RuntimeError(f"{context}: download target entries must be objects")
        normalized_targets.append(_normalize_download_target(target, context=context))
    return tuple(normalized_targets)


def _resolve_cache_directory(
    cache_root: Path,
    spec: Mapping[str, ConfigValue],
    *,
    tool_name: str,
    version: str | None,
) -> Path:
    """Return the cache directory for the specified tool/version combination.

    Args:
        cache_root: Root cache directory configured by the caller.
        spec: Download specification containing optional cache overrides.
        tool_name: Normalised tool name used as the cache key.
        version: Optional version string appended to the cache path.

    Returns:
        Path: Directory path where the artifact should be stored.
    """

    cache_dir = str(spec.get("cacheSubdir", tool_name)).strip() or tool_name
    base_dir = cache_root / cache_dir
    if version:
        base_dir /= version
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _determine_filename(target: _DownloadTarget) -> str:
    """Return the filename that should be used for ``target``.

    Args:
        target: Download target describing the artifact.

    Returns:
        str: Filename derived from explicit metadata or the source URL.
    """

    return target.filename or target.member or _filename_from_url(target.url)


def _fetch_artifact(url: str, *, timeout: int) -> _HttpResponse:
    """Return the HTTP response for the artifact located at ``url``.

    Args:
        url: Artifact download URL.
        timeout: Timeout in seconds applied to the HTTP request.

    Returns:
        _HttpResponse: Response object ready for content consumption.
    """

    get = _load_requests_get()
    response = get(url, timeout=timeout)
    response.raise_for_status()
    return response


def _write_artifact_content(
    response: _HttpResponse,
    target: _DownloadTarget,
    destination: Path,
    *,
    context: str,
) -> None:
    """Write the artifact content from ``response`` to ``destination``.

    Args:
        response: HTTP response containing the artifact payload.
        target: Download target describing the archive structure.
        destination: Filesystem path where the artifact will be stored.
        context: Human-readable context used for error reporting.
    """

    if target.archive_format is None:
        destination.write_bytes(response.content)
        return
    if target.archive_format == TAR_GZ_ARCHIVE:
        _extract_tar_member(response.content, target, destination, context=context)
        return
    raise RuntimeError(f"{context}: unsupported archive format '{target.archive_format}'")


def _make_executable(path: Path) -> None:
    """Set executable permissions on ``path`` for user/group/other.

    Args:
        path: Path to the downloaded artifact.
    """

    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _normalize_download_target(
    data: Mapping[str, ConfigValue],
    *,
    context: str,
) -> _DownloadTarget:
    """Validate and normalise a single download target specification.

    Args:
        data: Mapping describing the download target.
        context: Human-readable context used for error reporting.

    Returns:
        _DownloadTarget: Normalised download target structure.
    """

    url_value = data.get("url")
    if not isinstance(url_value, str) or not url_value:
        raise RuntimeError(f"{context}: download target requires a non-empty 'url'")

    os_value = data.get("os") or data.get("oses")
    os_list = _normalize_string_sequence(os_value, context=context) if os_value is not None else None
    arch_value = data.get("arch") or data.get("architectures")
    arch_list = _normalize_string_sequence(arch_value, context=context) if arch_value is not None else None

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


def _normalize_string_sequence(value: ConfigValue, *, context: str) -> tuple[str, ...]:
    """Return a tuple of strings parsed from ``value``.

    Args:
        value: Configuration value expected to represent a string sequence.
        context: Human-readable context used for error reporting.

    Returns:
        tuple[str, ...]: Tuple of lower-cased string values.

    Raises:
        RuntimeError: If ``value`` cannot be interpreted as a string sequence.
    """

    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise RuntimeError(f"{context}: download target entries must be strings")
            result.append(item)
        return tuple(result)
    raise RuntimeError(f"{context}: download target sequences must be arrays of strings")


def _select_download_target(targets: Sequence[_DownloadTarget], *, context: str) -> _DownloadTarget:
    """Select the best download target for the current platform.

    Args:
        targets: Candidate download targets.
        context: Human-readable context used for error reporting.

    Returns:
        _DownloadTarget: Matching target for the host platform.

    Raises:
        RuntimeError: If no compatible target is available.
    """

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
    """Return normalised architecture identifier derived from ``machine``.

    Args:
        machine: Raw architecture string reported by the platform.

    Returns:
        str: Normalised architecture identifier.
    """

    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return "x86_64"
    if normalized in {"aarch64", "arm64"}:
        return "arm64"
    return normalized


def _filename_from_url(url: str) -> str:
    """Return the filename component extracted from ``url``.

    Args:
        url: Download URL.

    Returns:
        str: Final path component derived from the URL.
    """

    return url.rstrip("/").split("/")[-1]


class _DownloadFormatProxy(dict[str, str]):
    """Dictionary proxy used to provide default values for format placeholders."""

    def __init__(self, *, version: str | None) -> None:
        """Initialise the format proxy with optional version metadata.

        Args:
            version: Optional version string used for placeholder expansion.
        """

        super().__init__()
        if version is not None:
            self["version"] = version

    def __missing__(self, key: str) -> str:
        """Return the default value for missing placeholders.

        Args:
            key: Placeholder name that was not provided.

        Returns:
            str: Empty string to avoid formatting failures.
        """

        return ""


def _extract_tar_member(
    content: bytes,
    target: _DownloadTarget,
    destination: Path,
    *,
    context: str,
) -> None:
    """Extract a gzipped tar archive member into ``destination``.

    Args:
        content: Raw ``.tar.gz`` archive bytes.
        target: Download target describing the desired archive member.
        destination: Destination path for the extracted file.
        context: Human-readable context used for error reporting.
    """

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


def _normalize_timeout(value: ConfigValue, *, context: str) -> int:
    """Coerce the timeout value into an integer number of seconds.

    Args:
        value: Timeout value supplied by the catalog configuration.
        context: Human-readable context used for error reporting.

    Returns:
        int: Timeout value expressed in whole seconds.

    Raises:
        RuntimeError: If ``value`` cannot be interpreted as a positive number.
    """

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
    """Extract the requested archive member and return the extracted path.

    Args:
        archive: Open tar archive containing the artifact.
        member_name: Explicit member to extract or ``None`` to select automatically.
        scratch_dir: Temporary directory that receives the extracted file.
        context: Human-readable context used for error reporting.

    Returns:
        Path: Path to the extracted file within ``scratch_dir``.
    """

    selected_member = _select_tar_member(archive, member_name=member_name, context=context)
    archive.extract(selected_member, path=scratch_dir, filter="data")
    return scratch_dir / selected_member.name


def _select_tar_member(
    archive: tarfile.TarFile,
    *,
    member_name: str | None,
    context: str,
) -> tarfile.TarInfo:
    """Select a tarfile member either by name or the first regular file.

    Args:
        archive: Open tar archive containing the artifact.
        member_name: Explicit member to extract or ``None`` to select automatically.
        context: Human-readable context used for error reporting.

    Returns:
        tarfile.TarInfo: Selected tar member ready for extraction.

    Raises:
        RuntimeError: If the requested member is missing or the archive lacks files.
    """

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
    """Convert ``gofmt --list`` output into diagnostics describing unformatted files.

    Args:
        stdout: Lines produced by ``gofmt --list``.
        _context: Tool execution context (unused for gofmt diagnostics).

    Returns:
        list[RawDiagnostic]: Diagnostics indicating files that require formatting.
    """
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
