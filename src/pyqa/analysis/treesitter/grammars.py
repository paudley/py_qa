# SPDX-License-Identifier: MIT
"""Helpers for resolving Tree-sitter grammars when packaged modules are missing."""

from __future__ import annotations

import importlib
import os
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter import Language

_CACHE_ROOT = Path(os.environ.get("PYQA_TREESITTER_CACHE", Path.home() / ".cache" / "pyqa" / "tree_sitter"))


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


def ensure_language(grammar_name: str) -> Language | None:
    """Return a :class:`Language` instance for ``grammar_name`` if available."""

    module_name = f"tree_sitter_{grammar_name.replace('-', '_')}"
    module = _import_language_module(module_name)
    if module is not None:
        language = _language_from_module(module)
        if language is not None:
            return language

    source = _GRAMMAR_SOURCES.get(grammar_name)
    if source is None or not hasattr(Language, "build_library"):
        return None

    cache_dir = _CACHE_ROOT / grammar_name
    lib_path = cache_dir / _library_filename(grammar_name)
    if not lib_path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _build_language_library(source, lib_path, cache_dir)
    if not lib_path.exists():
        return None
    return Language(str(lib_path), grammar_name)


def _build_language_library(source: GrammarSource, lib_path: Path, cache_dir: Path) -> None:
    """Download and compile the Tree-sitter grammar archive."""

    archive_path = cache_dir / "grammar.tar.gz"
    if not archive_path.exists():
        _download(source.url, archive_path)

    with tempfile.TemporaryDirectory(dir=cache_dir) as extract_dir:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)
        grammar_dir = Path(extract_dir) / source.archive_subdir
        if not grammar_dir.exists():
            return
        try:
            Language.build_library(str(lib_path), [str(grammar_dir)])
        except (OSError, RuntimeError) as exc:
            if lib_path.exists():
                lib_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to compile Tree-sitter grammar for '{lib_path.stem}': {exc}") from exc


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        handle.write(response.read())


def _library_filename(grammar_name: str) -> str:
    if sys.platform.startswith("win"):
        return f"{grammar_name}.dll"
    if sys.platform == "darwin":
        return f"lib{grammar_name}.dylib"
    return f"lib{grammar_name}.so"


def _import_language_module(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def _language_from_module(module: Any) -> Language | None:
    factory = getattr(module, "language", None)
    if not callable(factory):
        return None
    return Language(factory())


__all__ = ["ensure_language"]
