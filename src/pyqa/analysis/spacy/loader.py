# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""spaCy language loading utilities and supporting protocols."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Iterator
from importlib import import_module
from shutil import which
from typing import Any, Final, Protocol, cast, runtime_checkable


@runtime_checkable
class TokenLike(Protocol):
    """Protocol describing the spaCy token API relied upon by pyqa."""

    @property
    def text(self) -> str:
        """Return the raw token text value."""

        raise NotImplementedError  # pragma: no cover - protocol definition

    @property
    def idx(self) -> int:
        """Return the character offset in the original document."""

        raise NotImplementedError  # pragma: no cover - protocol definition

    @property
    def is_stop(self) -> bool:
        """Return ``True`` when the token represents a stop word."""

        raise NotImplementedError  # pragma: no cover - protocol definition

    @property
    def pos_(self) -> str:
        """Return the coarse part-of-speech tag for the token."""

        raise NotImplementedError  # pragma: no cover - protocol definition

    @property
    def lemma_(self) -> str:
        """Return the lemmatised token form."""

        raise NotImplementedError  # pragma: no cover - protocol definition

    def __len__(self) -> int:
        """Return the number of characters comprising the token."""

        raise NotImplementedError  # pragma: no cover - protocol definition


@runtime_checkable
class DocLike(Protocol):
    """Protocol representing iterable spaCy documents used in analysis."""

    def __iter__(self) -> Iterator[TokenLike]:  # pragma: no cover - protocol definition
        """Return an iterator across contained tokens."""

        raise NotImplementedError

    def __len__(self) -> int:  # pragma: no cover - protocol definition
        """Return the number of tokens contained within the document."""

        raise NotImplementedError

    def __getitem__(self, index: int) -> TokenLike:  # pragma: no cover - protocol definition
        """Return the token located at ``index``."""

        raise NotImplementedError


class SpacyLanguage(Protocol):
    """Callable NLP pipeline contract used by pyqa."""

    def __call__(self, text: str) -> DocLike:  # pragma: no cover - protocol definition
        """Return a spaCy document for ``text``."""

        raise NotImplementedError

    def pipe(self, texts: Iterable[str]) -> Iterable[DocLike]:  # pragma: no cover - protocol definition
        """Return documents generated for ``texts`` in sequence."""

        raise NotImplementedError


_UNSET: Final[object] = object()
_LOADER_STATE: dict[str, object] = {"value": _UNSET}
_VERSION_STATE: dict[str, object] = {"value": _UNSET}


def load_language(model_name: str) -> SpacyLanguage | None:
    """Return a spaCy pipeline for ``model_name``, downloading it on demand.

    Args:
        model_name: Fully qualified spaCy model identifier.

    Returns:
        SpacyLanguage | None: Loaded pipeline callable or ``None`` when loading is
        not possible.
    """

    loader = _resolve_loader()
    if loader is None:
        return None
    try:
        return loader(model_name)
    except OSError:  # pragma: no cover - spaCy optional
        if _download_spacy_model(model_name):
            loader = _resolve_loader(force=True)
            if loader is None:
                return None
            try:
                return loader(model_name)
            except OSError:  # pragma: no cover - spaCy optional
                return None
    return None


def _download_spacy_model(model_name: str) -> bool:
    """Attempt to download the specified spaCy model via ``uv``.

    Args:
        model_name: Fully qualified spaCy model identifier.

    Returns:
        bool: ``True`` when the download completes successfully.
    """

    uv_path = which("uv")
    if not uv_path:
        return False

    version = _resolve_version()
    if not version:
        return False

    url = (
        "https://github.com/explosion/spacy-models/releases/download/"
        f"{model_name}-{version}/{model_name}-{version}-py3-none-any.whl"
    )

    try:
        completed = subprocess.run(
            [uv_path, "pip", "install", url],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False

    return completed.returncode == 0


def _resolve_loader(force: bool = False) -> Callable[[str], SpacyLanguage] | None:
    """Return the cached spaCy loader when available.

    Args:
        force: When ``True`` the loader is re-imported even if cached.

    Returns:
        Callable[[str], SpacyLanguage] | None: The loader callable or ``None``
        when spaCy is not installed.
    """

    cached = _LOADER_STATE["value"]
    if not force and cached is not _UNSET:
        return cast(Callable[[str], SpacyLanguage] | None, cached)
    try:
        module = import_module("spacy")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        _LOADER_STATE["value"] = None
        return None
    load_fn: Any = getattr(module, "load", None)
    if not callable(load_fn):
        _LOADER_STATE["value"] = None
        return None
    loader = cast(Callable[[str], SpacyLanguage], load_fn)
    _LOADER_STATE["value"] = loader
    return loader


def _resolve_version(force: bool = False) -> str | None:
    """Return the spaCy version string when available.

    Args:
        force: When ``True`` the version information is re-imported.

    Returns:
        str | None: Resolved spaCy version or ``None`` if unavailable.
    """

    cached = _VERSION_STATE["value"]
    if not force and cached is not _UNSET:
        return cast(str | None, cached)
    try:
        module = import_module("spacy")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        _VERSION_STATE["value"] = None
        return None
    version = getattr(module, "__version__", None)
    resolved = version if isinstance(version, str) else None
    _VERSION_STATE["value"] = resolved
    return resolved


__all__ = [
    "DocLike",
    "SpacyLanguage",
    "TokenLike",
    "load_language",
]
