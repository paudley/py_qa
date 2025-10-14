# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Resolve Tree-sitter grammars without depending on ``tree-sitter-languages``."""

from __future__ import annotations

import ctypes
import importlib
import os
import ssl
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import Final, cast
from urllib.parse import urlparse

from tree_sitter import Language as TSLanguage

_CACHE_ROOT: Final[Path] = Path(
    os.environ.get("PYQA_TREESITTER_CACHE", Path.home() / ".cache" / "pyqa" / "tree_sitter")
)
_SUPPORTED_SCHEMES: Final[frozenset[str]] = frozenset({"https"})
_LANGUAGE_SYMBOL_PREFIX: Final[str] = "tree_sitter_"
_DARWIN_PLATFORM: Final[str] = "darwin"

# Keep shared library handles alive so ctypes does not unload them prematurely.
_LOADED_LIBRARIES: dict[Path, ctypes.CDLL] = {}
_LANGUAGE_CACHE: dict[str, TSLanguage] = {}
_LANGUAGE_CACHE_LOCK = Lock()


@dataclass(frozen=True)
class GrammarSource:
    """Describe how to retrieve a Tree-sitter grammar from upstream."""

    url: str
    archive_subdir: str


# Minimal mapping covering grammars we expect to use frequently. Additional languages
# can be added incrementally.
_GRAMMAR_SOURCES: dict[str, GrammarSource] = {
    "python": GrammarSource(
        url="https://github.com/tree-sitter/tree-sitter-python/archive/refs/tags/v0.20.4.tar.gz",
        archive_subdir="tree-sitter-python-0.20.4",
    ),
}


def ensure_language(grammar_name: str) -> TSLanguage | None:
    """Resolve a :class:`Language` for ``grammar_name`` when possible.

    Args:
        grammar_name: Canonical Tree-sitter grammar name (e.g., ``"python"``).

    Returns:
        Language | None: Compiled grammar if loadable, otherwise ``None``.
    """

    with _LANGUAGE_CACHE_LOCK:
        cached = _LANGUAGE_CACHE.get(grammar_name)
        if cached is not None:
            return cached

    module_name = f"tree_sitter_{grammar_name.replace('-', '_')}"
    module = _import_language_module(module_name)
    if module is not None:
        language = _language_from_module(module)
        if language is not None:
            with _LANGUAGE_CACHE_LOCK:
                _LANGUAGE_CACHE.setdefault(grammar_name, language)
                return _LANGUAGE_CACHE[grammar_name]

    source = _GRAMMAR_SOURCES.get(grammar_name)
    if source is None:
        return None

    cache_dir = _CACHE_ROOT / grammar_name
    lib_path = cache_dir / _library_filename(grammar_name)
    if not lib_path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _build_language_library(source, lib_path, cache_dir)
    if not lib_path.exists():
        return None
    language = _load_compiled_language(lib_path, grammar_name)
    if language is not None:
        with _LANGUAGE_CACHE_LOCK:
            _LANGUAGE_CACHE.setdefault(grammar_name, language)
            return _LANGUAGE_CACHE[grammar_name]
    return None


def _build_language_library(source: GrammarSource, lib_path: Path, cache_dir: Path) -> None:
    """Compile a Tree-sitter grammar archive into ``lib_path``.

    Args:
        source: Remote grammar archive metadata.
        lib_path: Destination for the compiled shared library.
        cache_dir: Cache directory used for downloads and temporary files.
    """

    archive_path = cache_dir / "grammar.tar.gz"
    if not archive_path.exists():
        _download(source.url, archive_path)

    with tempfile.TemporaryDirectory(dir=cache_dir) as extract_dir:
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extract_tar(tar, Path(extract_dir))
        grammar_dir = Path(extract_dir) / source.archive_subdir
        if not grammar_dir.exists():
            return
        build_library = _resolve_build_library()
        if build_library is None:
            return
        try:
            build_library(str(lib_path), [str(grammar_dir)])
        except (OSError, RuntimeError) as exc:
            if lib_path.exists():
                lib_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to compile Tree-sitter grammar for '{lib_path.stem}': {exc}") from exc


def _download(url: str, destination: Path) -> None:
    """Download ``url`` into ``destination`` enforcing safe schemes.

    Args:
        url: HTTPS URL pointing to the grammar archive.
        destination: File path where the archive will be stored.
    """

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported download scheme '{parsed.scheme}' for Tree-sitter archive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "pyqa-tree-sitter/1.0"})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(request) as response, destination.open("wb") as handle:
        handle.write(response.read())


def _library_filename(grammar_name: str) -> str:
    """Return platform-specific shared library filename for ``grammar_name``."""

    if sys.platform.startswith("win"):
        return f"{grammar_name}.dll"
    if sys.platform == _DARWIN_PLATFORM:
        return f"lib{grammar_name}.dylib"
    return f"lib{grammar_name}.so"


def _import_language_module(module_name: str) -> ModuleType | None:
    """Import a packaged Tree-sitter language module when available."""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def _language_from_module(module: ModuleType) -> TSLanguage | None:
    """Instantiate a ``Language`` object from a packaged module factory."""

    factory = getattr(module, "language", None)
    if not callable(factory):
        return None
    pointer = factory()
    return TSLanguage(pointer)


def _resolve_build_library() -> Callable[[str, list[str]], None] | None:
    """Return the Tree-sitter build helper when exposed by the bindings."""

    candidate = getattr(TSLanguage, "build_library", None)
    if candidate is None or not callable(candidate):
        return None
    return cast(Callable[[str, list[str]], None], candidate)


def _safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    """Safely extract ``archive`` into ``destination`` preventing path escapes."""

    destination = destination.resolve()
    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError(f"Unsafe path detected in archive: {member.name}")
    for member in archive.getmembers():
        archive.extract(member, path=destination)


def _load_compiled_language(lib_path: Path, grammar_name: str) -> TSLanguage | None:
    """Load the compiled Tree-sitter ``Language`` from ``lib_path``.

    Args:
        lib_path: Path to the compiled shared library.
        grammar_name: Name of the grammar, used to select the exported symbol.

    Returns:
        TSLanguage | None: Loaded language instance or ``None`` when unavailable.
    """

    try:
        handle = ctypes.CDLL(str(lib_path))
    except OSError:
        return None
    symbol_name = f"{_LANGUAGE_SYMBOL_PREFIX}{grammar_name.replace('-', '_')}"
    factory = getattr(handle, symbol_name, None)
    if factory is None:
        return None
    factory.restype = ctypes.c_void_p
    pointer = factory()
    if not pointer:
        return None
    _LOADED_LIBRARIES[lib_path] = handle
    return TSLanguage(pointer)


__all__ = ["ensure_language"]
