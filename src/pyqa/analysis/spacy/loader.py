# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""spaCy language loading utilities and supporting protocols."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from importlib import import_module
from shutil import which
from threading import Lock
from types import ModuleType
from typing import Final, Protocol, cast, runtime_checkable


@runtime_checkable
class TokenLike(Protocol):
    """Define the spaCy token API relied upon by pyqa."""

    @property
    def text(self) -> str:
        """Return the raw token text value.

        Returns:
            str: Raw token text value.
        """

        return ""

    @property
    def idx(self) -> int:
        """Return the character offset in the original document.

        Returns:
            int: Character offset within the original document.
        """

        return 0

    @property
    def is_stop(self) -> bool:
        """Return ``True`` when the token represents a stop word.

        Returns:
            bool: ``True`` when the token is a stop word.
        """

        return False

    @property
    def pos_(self) -> str:
        """Return the coarse part-of-speech tag for the token.

        Returns:
            str: Coarse part-of-speech tag.
        """

        return ""

    @property
    def lemma_(self) -> str:
        """Return the lemmatised token form.

        Returns:
            str: Lemmatised token form.
        """

        return ""

    def __len__(self) -> int:
        """Return the number of characters comprising the token.

        Returns:
            int: Character count of the token.
        """

        return 0


@runtime_checkable
class DocLike(Protocol):
    """Define iterable spaCy document behaviour used in analysis."""

    def __iter__(self) -> Iterator[TokenLike]:
        """Return an iterator across contained tokens.

        Returns:
            Iterator[TokenLike]: Iterator across contained tokens.
        """

        return iter(cast(tuple[TokenLike, ...], ()))

    def __len__(self) -> int:
        """Return the number of tokens contained within the document.

        Returns:
            int: Token count contained within the document.
        """

        return 0

    def __getitem__(self, index: int) -> TokenLike:
        """Return the token located at ``index``.

        Args:
            index: Position of the requested token.

        Returns:
            TokenLike: Token located at the requested index.
        """

        return cast(TokenLike, object())


class SpacyLanguage(Protocol):
    """Define callable NLP pipeline contract used by pyqa."""

    def __call__(self, text: str) -> DocLike:
        """Return a spaCy document for ``text``.

        Args:
            text: Text to convert into a document.

        Returns:
            DocLike: spaCy document representing ``text``.
        """

        return cast(DocLike, object())

    def pipe(self, texts: Iterable[str]) -> Iterable[DocLike]:
        """Return documents generated for ``texts`` in sequence.

        Args:
            texts: Iterable of text fragments to process.

        Returns:
            Iterable[DocLike]: Documents produced for ``texts``.
        """

        return cast(Iterable[DocLike], ())


@dataclass(frozen=True)
class _UnsetSentinel:
    """Represent an uninitialised cache entry sentinel."""


_SENTINEL: Final[_UnsetSentinel] = _UnsetSentinel()


@dataclass(slots=True)
class _LoaderState:
    """Maintain cached spaCy loader and version metadata."""

    loader: Callable[[str], SpacyLanguage] | None | _UnsetSentinel = _SENTINEL
    version: str | None | _UnsetSentinel = _SENTINEL
    language_cache: dict[str, SpacyLanguage] = field(default_factory=dict)
    language_lock: Lock = field(default_factory=Lock)


_STATE = _LoaderState()


def load_language(model_name: str) -> SpacyLanguage | None:
    """Return a spaCy pipeline for ``model_name``, downloading it on demand.

    Args:
        model_name: Fully qualified spaCy model identifier.

    Returns:
        SpacyLanguage | None: Loaded pipeline callable or ``None`` when loading is
        not possible.
    """

    with _STATE.language_lock:
        if model_name in _STATE.language_cache:
            return _STATE.language_cache[model_name]
    loader = _resolve_loader()
    if loader is None:
        return None
    language: SpacyLanguage
    try:
        language = loader(model_name)
    except OSError:  # pragma: no cover - spaCy optional
        if not _download_spacy_model(model_name):
            return None
        loader = _resolve_loader(force=True)
        if loader is None:
            return None
        try:
            language = loader(model_name)
        except OSError:  # pragma: no cover - spaCy optional
            return None
    with _STATE.language_lock:
        cached = _STATE.language_cache.get(model_name)
        if cached is None:
            _STATE.language_cache[model_name] = language
            cached = language
    return cached


def _download_spacy_model(model_name: str) -> bool:
    """Download the specified spaCy model via ``uv`` when available.

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

    if not force and _STATE.loader is not _SENTINEL:
        return cast(Callable[[str], SpacyLanguage] | None, _STATE.loader)
    try:
        module: ModuleType = import_module("spacy")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        _STATE.loader = None
        return None
    load_fn = getattr(module, "load", None)
    if not callable(load_fn):
        _STATE.loader = None
        return None
    loader = cast(Callable[[str], SpacyLanguage], load_fn)
    _STATE.loader = loader
    return loader


def _resolve_version(force: bool = False) -> str | None:
    """Return the spaCy version string when available.

    Args:
        force: When ``True`` the version information is re-imported.

    Returns:
        str | None: Resolved spaCy version or ``None`` if unavailable.
    """

    if not force and _STATE.version is not _SENTINEL:
        return cast(str | None, _STATE.version)
    try:
        module: ModuleType = import_module("spacy")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        _STATE.version = None
        return None
    version = getattr(module, "__version__", None)
    resolved = version if isinstance(version, str) else None
    _STATE.version = resolved
    return resolved


__all__ = [
    "DocLike",
    "SpacyLanguage",
    "TokenLike",
    "load_language",
]
