# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""spaCy language loading utilities and supporting protocols."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from importlib import import_module
from shutil import which
from threading import Lock
from types import ModuleType
from typing import Final, Protocol, cast, runtime_checkable

from pyqa.core.logging.public import warn as log_warn


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
        """Generate documents for ``texts`` in sequence.

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
    language_cache: dict[str, SpacyLanguage] = field(default_factory=dict)
    language_lock: Lock = field(default_factory=Lock)


_STATE = _LoaderState()
_INSTALL_HINT = "Run `uv run python -m spacy download {model}` to install the missing model."


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
        _warn_spacy_unavailable(model_name, "spaCy is not installed in the current environment")
        return None

    language, error = _attempt_load(loader, model_name)
    if language is None:
        if not _download_spacy_model(model_name):
            detail = _format_error(error) or "automatic download failed"
            _warn_spacy_unavailable(model_name, detail)
            return None
        loader = _resolve_loader(force=True)
        if loader is None:
            _warn_spacy_unavailable(model_name, "spaCy could not be re-imported after downloading the model")
            return None
        language, error = _attempt_load(loader, model_name)
        if language is None:
            detail = _format_error(error) or "spaCy still cannot load the requested model"
            _warn_spacy_unavailable(model_name, detail)
            return None
    with _STATE.language_lock:
        cached = _STATE.language_cache.get(model_name)
        if cached is None:
            _STATE.language_cache[model_name] = language
            cached = language
    return cached


def _download_spacy_model(model_name: str) -> bool:
    """Retrieve the specified spaCy model using the most reliable command available.

    Args:
        model_name: Fully qualified spaCy model identifier.

    Returns:
        bool: ``True`` when the download completes successfully.
    """

    uv_path = which("uv")
    python_executable = sys.executable or "python"
    commands: list[list[str]] = []

    if uv_path:
        commands.append([uv_path, "run", "python", "-m", "spacy", "download", model_name])
        commands.append([uv_path, "pip", "install", model_name])

    commands.append([python_executable, "-m", "spacy", "download", model_name])
    commands.append([python_executable, "-m", "pip", "install", model_name])
    commands.append(["python", "-m", "spacy", "download", model_name])
    commands.append(["python", "-m", "pip", "install", model_name])

    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(command)
        if key in seen:
            continue
        seen.add(key)
        if _run_subprocess(command):
            return True
    return False


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


def _run_subprocess(command: list[str]) -> bool:
    """Execute ``command`` returning ``True`` when it succeeds."""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:  # pragma: no cover - environment-specific failure
        return False
    return completed.returncode == 0


def _attempt_load(
    loader: Callable[[str], SpacyLanguage],
    model_name: str,
) -> tuple[SpacyLanguage | None, BaseException | None]:
    """Invoke ``loader`` catching ``OSError`` when the model is missing."""

    try:
        return loader(model_name), None
    except OSError as exc:  # pragma: no cover - depends on optional spaCy model
        return None, exc


def _format_error(error: BaseException | None) -> str:
    """Return a concise error description for warning messages."""

    if error is None:
        return ""
    message = str(error).strip()
    return message or error.__class__.__name__


def _warn_spacy_unavailable(model_name: str, detail: str) -> None:
    """Emit a loud warning describing how to resolve missing spaCy support."""

    log_warn(
        (
            f"spaCy isn't fully installed ({detail}). Key docstring and annotation features "
            f"are disabled until the '{model_name}' model is available. "
            f"{_INSTALL_HINT.format(model=model_name)}"
        ),
        use_emoji=True,
    )


__all__ = [
    "DocLike",
    "SpacyLanguage",
    "TokenLike",
    "load_language",
]
