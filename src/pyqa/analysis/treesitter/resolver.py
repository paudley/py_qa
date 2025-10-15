# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Context extraction using Tree-sitter grammars."""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Final, cast

from pydantic import BaseModel, ConfigDict
from tree_sitter import Language as TSLanguage
from tree_sitter import Node as TSNode
from tree_sitter import Parser as TSParser
from tree_sitter import Tree as TSTree

from pyqa.cache.in_memory import memoize

from ...core.logging import warn
from ...core.models import Diagnostic
from ..treesitter.grammars import ensure_language

EnsureLanguageCallable = Callable[[str], TSLanguage | None]

_ENSURE_LANGUAGE: EnsureLanguageCallable | None = ensure_language

MARKDOWN_HEADING_NODE_TYPE: Final[str] = "heading"
JSON_PAIR_NODE_TYPE: Final[str] = "pair"


class _ParseResult(BaseModel):
    tree: TSTree
    source: bytes

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Language(str, Enum):
    """Enumerate languages supported by the context resolver."""

    PYTHON = "python"
    MARKDOWN = "markdown"
    JSON = "json"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    SQL = "sql"
    YAML = "yaml"
    SHELL = "shell"
    LUA = "lua"
    PHP = "php"
    TOML = "toml"
    DOCKERFILE = "dockerfile"
    MAKE = "make"


@dataclass(frozen=True)
class ParserFactory:
    """Factory capable of constructing tree-sitter parsers on demand."""

    parser_cls: Callable[[], TSParser] | None
    get_parser: Callable[[str], TSParser] | None
    language_cls: type[TSLanguage] | None

    def create(
        self,
        grammar_name: str,
        *,
        register_warning: Callable[[str], None] | None = None,
    ) -> TSParser | None:
        """Build a parser capable of handling ``grammar_name``.

        Args:
            grammar_name: Canonical Tree-sitter grammar name to load.
            register_warning: Optional callback used to surface warning messages.

        Returns:
            TSParser | None: Parser configured with the requested language, or ``None``
            when the parser cannot be created.
        """

        if self.get_parser is not None:
            return self.get_parser(grammar_name)
        if self.language_cls is None:
            return None
        module_name = f"tree_sitter_{grammar_name.replace('-', '_')}"
        module = self._import_language_module(module_name)
        language = (
            self._build_language(module)
            if module is not None
            else self._compile_language(grammar_name, register_warning=register_warning)
        )
        parser = self._build_parser()
        if language is None or parser is None:
            return None
        return self._assign_language(parser, language)

    def _build_language(self, module: ModuleType) -> TSLanguage | None:
        """Construct a Tree-sitter language from a packaged module.

        Args:
            module: Imported grammar module exposing a ``language`` factory.

        Returns:
            TSLanguage | None: Instantiated language object when the factory succeeds.
        """

        language_factory = getattr(module, "language", None)
        if not callable(language_factory) or self.language_cls is None:
            return None
        try:
            return self.language_cls(language_factory())
        except (TypeError, ValueError):
            return None

    def _compile_language(
        self,
        grammar_name: str,
        *,
        register_warning: Callable[[str], None] | None,
    ) -> TSLanguage | None:
        """Compile grammar sources when bundled modules are unavailable.

        Args:
            grammar_name: Canonical Tree-sitter grammar name to compile.
            register_warning: Optional callback used to record warnings.

        Returns:
            TSLanguage | None: Compiled language when successful; otherwise ``None``.
        """

        if _ENSURE_LANGUAGE is None:
            self._emit_warning(
                register_warning,
                f"Tree-sitter grammar '{grammar_name}' missing and auto-compilation helpers are unavailable.",
            )
            return None
        try:
            language = _ENSURE_LANGUAGE(grammar_name)
        except RuntimeError as exc:
            self._emit_warning(
                register_warning,
                f"Failed to compile Tree-sitter grammar '{grammar_name}': {exc}",
            )
            return None
        if language is None:
            self._emit_warning(
                register_warning,
                f"Tree-sitter grammar '{grammar_name}' could not be compiled automatically.",
            )
            return None
        return language

    def _build_parser(self) -> TSParser | None:
        """Instantiate a parser using the configured parser factory.

        Returns:
            TSParser | None: Parser instance when creation succeeds; otherwise ``None``.
        """

        parser_factory = self.parser_cls
        if parser_factory is None:
            return None
        try:
            return parser_factory()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _import_language_module(module_name: str) -> ModuleType | None:
        """Import the Tree-sitter language module when it is installed.

        Args:
            module_name: Fully-qualified module name to import.

        Returns:
            ModuleType | None: Imported module or ``None`` if the module cannot be located.
        """

        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            return None

    @staticmethod
    def _assign_language(parser: TSParser, language: TSLanguage) -> TSParser | None:
        """Attach ``language`` to ``parser`` returning the parser when successful.

        Args:
            parser: Parser instance produced by the Tree-sitter bindings.
            language: Language object returned by ``create``.

        Returns:
            TSParser | None: Parser after assignment, or ``None`` when assignment fails.
        """

        setter = getattr(parser, "set_language", None)
        if callable(setter):
            setter(language)
            return parser
        if hasattr(parser, "language"):
            try:
                setattr(parser, "language", language)
            except (AttributeError, TypeError, ValueError):
                return None
            return parser
        return None

    @staticmethod
    def _emit_warning(register_warning: Callable[[str], None] | None, message: str) -> None:
        """Forward ``message`` to ``register_warning`` or log directly.

        Args:
            register_warning: Optional callback that records warning messages.
            message: Warning text to surface to the caller.
        """

        if register_warning is not None:
            register_warning(message)
        else:
            warn(message, use_emoji=True)


def _build_parser_loader() -> ParserFactory | None:
    """Return a parser factory when tree-sitter bindings are available."""

    tree_sitter_module = importlib.import_module("tree_sitter")
    parser_cls = getattr(tree_sitter_module, "Parser", None)
    if parser_cls is None:
        raise RuntimeError(
            "tree_sitter.Parser is unavailable; upgrade the tree-sitter package",
        )

    language_cls = getattr(tree_sitter_module, "Language", None)

    try:
        bundled = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        if language_cls is None:
            return None
        return ParserFactory(parser_cls=parser_cls, get_parser=None, language_cls=language_cls)

    get_parser_attr = getattr(bundled, "get_parser", None)
    if not callable(get_parser_attr):
        raise RuntimeError(
            "tree_sitter_languages.get_parser is unavailable; reinstall tree-sitter-languages",
        )
    bundled_get_parser = cast(Callable[[str], TSParser], get_parser_attr)
    return ParserFactory(
        parser_cls=parser_cls,
        get_parser=bundled_get_parser,
        language_cls=language_cls,
    )


@dataclass(slots=True)
class _ParserLoader:
    """Callable wrapper that constructs parsers and reports failures."""

    parser_factory: ParserFactory
    grammar_name: str
    register_warning: Callable[[str], None]

    def __call__(self) -> TSParser | None:
        """Return a parser for ``grammar_name`` or emit a warning on failure."""

        parser = self.parser_factory.create(
            self.grammar_name,
            register_warning=self.register_warning,
        )
        if parser is None:
            self.register_warning(
                f"Tree-sitter grammar '{self.grammar_name}' unavailable; falling back to heuristic context extraction.",
            )
        return parser


_PARSER_FACTORY = _build_parser_loader()


class TreeSitterContextResolver:
    """Enrich diagnostics with structural context using Tree-sitter."""

    _LANGUAGE_ALIASES: Final[dict[Language, tuple[str, ...]]] = {
        Language.PYTHON: (".py", ".pyi"),
        Language.MARKDOWN: (".md", ".markdown", ".mdx"),
        Language.JSON: (".json",),
        Language.JAVASCRIPT: (".js", ".jsx"),
        Language.TYPESCRIPT: (".ts", ".tsx"),
        Language.GO: (".go",),
        Language.RUST: (".rs",),
        Language.SQL: (".sql",),
        Language.YAML: (".yaml", ".yml"),
        Language.SHELL: (".sh", ".bash", ".zsh"),
        Language.LUA: (".lua",),
        Language.PHP: (".php", ".phtml"),
        Language.TOML: (".toml",),
        Language.MAKE: (".mk",),
    }

    _SPECIAL_FILENAMES: Final[dict[str, Language]] = {
        "dockerfile": Language.DOCKERFILE,
        "containerfile": Language.DOCKERFILE,
        "makefile": Language.MAKE,
    }

    _GRAMMAR_NAMES: Final[dict[Language, str]] = {
        Language.PYTHON: "python",
        Language.MARKDOWN: "markdown",
        Language.JSON: "json",
        Language.JAVASCRIPT: "javascript",
        Language.TYPESCRIPT: "typescript",
        Language.GO: "go",
        Language.RUST: "rust",
        Language.SQL: "sql",
        Language.YAML: "yaml",
        Language.SHELL: "bash",
        Language.LUA: "lua",
        Language.PHP: "php",
        Language.TOML: "toml",
        Language.DOCKERFILE: "dockerfile",
        Language.MAKE: "make",
    }

    _FALLBACK_LANGUAGES: Final[set[Language]] = {
        Language.PYTHON,
        Language.MARKDOWN,
        Language.JSON,
    }

    def __init__(self) -> None:
        self._parsers: dict[Language, TSParser] = {}
        self._disabled: set[Language] = set()
        self._warnings: set[str] = set()

    def grammar_modules(self) -> dict[str, str]:
        """Expose supported grammar modules for diagnostic tooling."""
        return {language.value: name for language, name in self._GRAMMAR_NAMES.items()}

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        """Populate ``diagnostic.function`` using structural context when available."""

        root_path = root.resolve()
        for diag in diagnostics:
            if diag.function or diag.line is None or not diag.file:
                continue
            language = self._detect_language(diag.file)
            if language is None:
                continue
            location = self._resolve_path(diag.file, root_path)
            if location is None or not location.is_file():
                continue
            context = self._find_context(language, location, diag.line)
            if context:
                diag.function = self._normalise_context(language, context)

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Return context strings for the requested ``lines``."""

        language = self._detect_language(file_path)
        if language is None:
            return {}
        location = self._resolve_path(file_path, root)
        if location is None or not location.is_file():
            return {}

        contexts: dict[int, str] = {}
        for line in lines:
            if line in contexts:
                continue
            context = self._find_context(language, location, line)
            if context:
                contexts[line] = self._normalise_context(language, context)
        return contexts

    def _detect_language(self, file_str: str) -> Language | None:
        """Return the language associated with ``file_str`` when known."""

        path = Path(file_str)
        suffix = path.suffix.lower()
        for language, suffixes in self._LANGUAGE_ALIASES.items():
            if suffix in suffixes:
                return language
        name = path.name.lower()
        return self._SPECIAL_FILENAMES.get(name)

    @staticmethod
    def _resolve_path(file_str: str, root: Path) -> Path | None:
        candidate = Path(file_str)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        return candidate

    def _get_parser(self, language: Language) -> TSParser | None:
        if language in self._disabled:
            return None
        cached = self._parsers.get(language)
        if cached is not None:
            return cached
        loader = self._resolve_parser_loader(language)
        if loader is None:
            return None
        try:
            parser = loader()
        except (ImportError, OSError, ValueError, RuntimeError):
            self._disable_language(language)
            return None
        if parser is None or not hasattr(parser, "parse"):
            self._disable_language(language)
            return None
        self._parsers[language] = parser
        return parser

    def _resolve_parser_loader(self, language: Language) -> _ParserLoader | None:
        """Return a parser factory for ``language`` when available.

        Args:
            language: Language enum identifying the requested parser.

        Returns:
            _ParserLoader | None: Zero-argument callable creating a parser or
            ``None`` when no parser can be produced.
        """

        factory = _PARSER_FACTORY
        if factory is None:
            self._register_warning("Tree-sitter parser unavailable; falling back to heuristic context extraction.")
            self._disable_language(language)
            return None
        grammar_name = self._GRAMMAR_NAMES.get(language)
        if grammar_name is None:
            self._disable_language(language)
            return None

        return _ParserLoader(
            parser_factory=factory,
            grammar_name=grammar_name,
            register_warning=self._register_warning,
        )

    def _disable_language(self, language: Language) -> None:
        if language not in self._FALLBACK_LANGUAGES:
            self._disabled.add(language)
        self._parsers.pop(language, None)

    def _register_warning(self, message: str) -> None:
        if message in self._warnings:
            return
        self._warnings.add(message)
        warn(message, use_emoji=True)

    def consume_warnings(self) -> list[str]:
        """Return and clear accumulated warning messages.

        Returns:
            list[str]: Sorted list of warning strings emitted since the last call.
        """

        warnings = sorted(self._warnings)
        self._warnings.clear()
        return warnings

    @memoize(maxsize=256)
    def _parse(self, language: Language, path: Path, _mtime_ns: int) -> _ParseResult | None:
        parser = self._get_parser(language)
        if parser is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        try:
            tree = parser.parse(source)
        except (ValueError, RuntimeError):
            return None
        return _ParseResult(tree=tree, source=source)

    def _find_context(self, language: Language, path: Path, line: int) -> str | None:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        parsed = self._parse(language, path, mtime_ns)
        if parsed is not None:
            tree_context = self._context_from_parse(language, parsed, line)
            if tree_context:
                return self._normalise_context(language, tree_context)
        context = self._fallback_context(language, path, line)
        return self._normalise_context(language, context) if context else None

    @staticmethod
    def _normalise_context(language: Language, context: str) -> str:
        if language is Language.MARKDOWN:
            stripped = context.lstrip("# ")
            return stripped or context
        return context

    def _context_from_parse(
        self,
        language: Language,
        parsed: _ParseResult,
        line: int,
    ) -> str | None:
        tree = getattr(parsed.tree, "root_node", None)
        if tree is None:
            return None
        if language is Language.PYTHON:
            return self._python_context(tree, line)
        if language is Language.MARKDOWN:
            return self._markdown_context(tree, line, parsed.source)
        if language is Language.JSON:
            node = self._node_at(tree, line)
            if node is not None:
                return self._json_context(node)
        return None

    def _fallback_context(self, language: Language, path: Path, line: int) -> str | None:
        if language is Language.PYTHON:
            context = self._python_ast_context(path, line)
            return context or self._python_fallback(path, line)
        if language is Language.MARKDOWN:
            context = self._markdown_heading_context(path, line)
            return context or self._markdown_fallback(path, line)
        if language is Language.JSON:
            return self._json_fallback(path, line)
        return None

    def _python_context(self, node: TSNode, line: int) -> str | None:
        """Return the most specific Python scope covering ``line``."""

        named_scope = _nearest_python_named_scope(node, line)
        if named_scope:
            return named_scope
        generic_node = _nearest_python_generic_node(node, line)
        if generic_node is None:
            return None
        fallback_name = _tree_node_name(generic_node)
        if fallback_name:
            return fallback_name
        node_type = getattr(generic_node, "type", None)
        return str(node_type) if isinstance(node_type, str) else None

    def _markdown_context(self, node: TSNode, line: int, source: bytes) -> str | None:
        """Return the Markdown heading that precedes ``line`` when available.

        Args:
            node: Tree-sitter node representing the parsed Markdown document.
            line: One-based line number for which context is requested.
            source: Raw Markdown bytes used to compute accurate headings.

        Returns:
            str | None: Sanitised heading text or ``None`` when no heading exists.
        """

        headings: list[tuple[int, str]] = []
        for current, depth in _iter_tree_nodes_with_depth(node):
            if getattr(current, "type", "") != MARKDOWN_HEADING_NODE_TYPE:
                continue
            current_start, current_end = _node_row_span(current)
            if current_start is None or current_end is None:
                continue
            if current_start > line:
                break
            heading_text = self._markdown_heading_text(current, depth, source)
            if heading_text:
                headings.append((current_start, heading_text))
        for current_line, heading in reversed(headings):
            if current_line <= line:
                return heading
        return None

    def _markdown_heading_text(self, node: TSNode, depth: int, source: bytes) -> str | None:
        """Return sanitised heading text for ``node`` with depth fallbacks.

        Args:
            node: Tree-sitter node representing a Markdown heading.
            depth: Zero-based depth supplied by the traversal helper.
            source: Raw Markdown bytes used for slicing heading text.

        Returns:
            str | None: Clean heading representation or ``None`` when unavailable.
        """

        level_hint = max(depth, 1)
        prefix = "#" * level_hint

        raw = _tree_node_name(node)
        if raw:
            stripped = raw.strip()
            cleaned = stripped.lstrip("# ").strip()
            return cleaned or f"{prefix} {stripped}".strip()
        slice_field = getattr(node, "child_by_field_name", None)
        if callable(slice_field):
            text_node = slice_field("text")
            if text_node is not None:
                text = getattr(text_node, "text", None)
                if isinstance(text, bytes):
                    decoded = text.decode("utf-8").strip()
                    cleaned = decoded.lstrip("# ").strip()
                    return cleaned or f"{prefix} {decoded}".strip()
        start = getattr(node, "start_byte", None)
        end = getattr(node, "end_byte", None)
        if isinstance(start, int) and isinstance(end, int):
            decoded = source[start:end].decode("utf-8", errors="ignore").strip()
            cleaned = decoded.lstrip("# ").strip()
            return cleaned or f"{prefix} {decoded}".strip()
        return None

    def _markdown_fallback(self, path: Path, line: int) -> str | None:
        """Return the nearest Markdown heading when the parse tree lacks context.

        Args:
            path: Filesystem path to the Markdown document under inspection.
            line: One-based line number for which context is requested.

        Returns:
            str | None: Heading text or ``None`` when no heading lines precede the
            requested line.
        """

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        headings: list[tuple[int, str]] = []
        for number, raw in enumerate(content.splitlines(), start=1):
            stripped = raw.strip()
            if stripped.startswith("#"):
                headings.append((number, stripped))
        for number, heading in reversed(headings):
            if number <= line:
                return heading
        return None

    def _markdown_heading_context(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        headings: list[tuple[int, str]] = []
        for number, raw in enumerate(content.splitlines(), start=1):
            stripped = raw.strip()
            if stripped.startswith("#"):
                headings.append((number, stripped))
        for number, heading in reversed(headings):
            if number <= line:
                return heading
        return None

    def _json_context(self, node: TSNode) -> str | None:
        parts: list[str] = []
        for current in _iter_tree_nodes(node):
            node_type = getattr(current, "type", "")
            if node_type == JSON_PAIR_NODE_TYPE:
                key_node = getattr(current, "child_by_field_name", None)
                if callable(key_node):
                    key_token = cast(TSNode | None, key_node("key"))
                else:
                    key_token = None
                key_name = _tree_node_name(key_token)
                if key_name:
                    parts.append(key_name)
        if not parts:
            return None
        return ".".join(parts)

    def _json_fallback(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        try:
            data = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        keys = list(data.keys())
        if not keys:
            return None
        index = min(max(line - 1, 0), len(keys) - 1)
        return str(keys[index])

    def _node_at(self, root: TSNode, line: int) -> TSNode | None:
        for node in _iter_tree_nodes(root):
            if _node_contains_line(node, line):
                return node
        return None

    def _python_ast_context(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        best_node: ast.AST | None = None
        best_start = -1
        for node in ast.walk(tree):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if start is None or end is None:
                continue
            if start <= line <= end:
                if start >= best_start:
                    best_node = node
                    best_start = start
        if isinstance(best_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return best_node.name
        return None

    @staticmethod
    def _python_fallback(path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        lines = content.splitlines()
        if not 1 <= line <= len(lines):
            return None
        raw = lines[line - 1].strip()
        return raw or None


def _tree_node_name(node: TSNode | None) -> str | None:
    """Return a normalised display name for ``node`` when available."""

    if node is None:
        return None

    extractor = getattr(node, "child_by_field_name", None)
    if callable(extractor):
        name_node = extractor("name")
        raw = getattr(name_node, "text", None)
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        if isinstance(raw, str):
            return raw
    text = getattr(node, "text", None)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _iter_tree_nodes(node: TSNode) -> Iterator[TSNode]:
    """Yield nodes in depth-first order starting from ``node``."""

    yield node
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes(child)


def _iter_tree_nodes_with_depth(node: TSNode, depth: int = 0) -> Iterator[tuple[TSNode, int]]:
    """Yield nodes and their depth in depth-first order."""

    yield node, depth
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes_with_depth(child, depth + 1)


def _node_row_span(node: TSNode) -> tuple[int | None, int | None]:
    """Return 1-based (start, end) line numbers for ``node`` when available."""

    start_point = getattr(node, "start_point", None)
    end_point = getattr(node, "end_point", None)
    start_row = start_point[0] + 1 if start_point else None
    end_row = end_point[0] + 1 if end_point else None
    return start_row, end_row


def _node_contains_line(node: TSNode, line: int) -> bool:
    """Return ``True`` when ``node`` spans ``line``."""

    start_row, end_row = _node_row_span(node)
    return bool(start_row is not None and end_row is not None and start_row <= line <= end_row)


def _nearest_python_named_scope(node: TSNode, line: int) -> str | None:
    """Return the innermost named Python scope covering ``line``."""

    best_line = -1
    best_name: str | None = None
    for current in _iter_tree_nodes(node):
        node_type = getattr(current, "type", "")
        if node_type not in {"function_definition", "class_definition"}:
            continue
        if not _node_contains_line(current, line):
            continue
        start_row, _ = _node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        name = _tree_node_name(current)
        if name:
            best_line = start_row
            best_name = name
    return best_name


def _nearest_python_generic_node(node: TSNode, line: int) -> TSNode | None:
    """Return the deepest node covering ``line`` when no named scope exists."""

    best_node: TSNode | None = None
    best_line = -1
    for current in _iter_tree_nodes(node):
        if not _node_contains_line(current, line):
            continue
        start_row, _ = _node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        best_line = start_row
        best_node = current
    return best_node


__all__ = ["TreeSitterContextResolver"]
