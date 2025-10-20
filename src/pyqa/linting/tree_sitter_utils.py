# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for working with Tree-sitter parsers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

from tree_sitter import Language, Parser

from ..analysis.treesitter.grammars import ensure_language
from ..analysis.treesitter.resolver import _build_parser_loader
from ..cache.in_memory import memoize

_LANGUAGE_TOKEN: Final[str] = "python"


@memoize(maxsize=1)
def load_python_language() -> Language:
    """Return the compiled Tree-sitter language for Python.

    Returns:
        Language: Compiled Tree-sitter language identifier for Python.

    Raises:
        RuntimeError: If the Python grammar cannot be located or compiled.
    """

    language = ensure_language(_LANGUAGE_TOKEN)
    if language is None:
        raise RuntimeError("Unable to compile or load the Python Tree-sitter grammar.")
    return language


def build_python_parser() -> Parser:
    """Return a new Tree-sitter parser configured for Python.

    Returns:
        Parser: Parser instance ready to parse Python source code.
    """

    parser = Parser()
    language = load_python_language()
    if hasattr(parser, "set_language"):
        setter = cast(Callable[[Language], None], getattr(parser, "set_language"))
        setter(language)
    else:
        setattr(parser, "language", language)
    return parser


def resolve_python_parser() -> Parser:
    """Return a Tree-sitter parser capable of parsing Python source.

    Returns:
        Parser: Parser configured for Python grammar.

    Raises:
        RuntimeError: If the Python grammar cannot be loaded.
    """

    factory = _build_parser_loader()
    if factory is not None:
        parser_candidate = factory.create(_LANGUAGE_TOKEN)
        if parser_candidate is not None:
            parser = parser_candidate
            language = load_python_language()
            if hasattr(parser, "set_language"):
                setter = cast(Callable[[Language], None], getattr(parser, "set_language"))
                setter(language)
            else:
                setattr(parser, "language", language)
            return parser
    return build_python_parser()


__all__ = ["load_python_language", "build_python_parser", "resolve_python_parser"]
