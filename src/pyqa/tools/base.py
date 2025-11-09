# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Definitions for lint tools and their actions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final, Literal, Protocol, TypeAlias, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from pyqa.interfaces.config import Config as ConfigProtocol
from tooling_spec.catalog.types import JSONValue as _CatalogJSONValue

from ..config.types import ConfigValue
from ..core.models import OutputFilter
from ..interfaces.tools import ToolConfiguration
from ..interfaces.tools import ToolContext as ToolContextProtocol
from .interfaces import (
    CommandBuilder,
    CommandBuilderContract,
    CommandBuilderLike,
    InstallerCallable,
    InternalActionRunner,
    Parser,
    ParserImplementation,
    ParserContract,
    ParserLike,
)

ConfigField: TypeAlias = ConfigProtocol | ToolConfiguration
ToolSettingsMap: TypeAlias = Mapping[str, ConfigValue]
ToolContextValue: TypeAlias = ConfigValue | Sequence[Path]
ToolContextExtras: TypeAlias = Mapping[str, ToolContextValue]
ToolContextPayloadValue: TypeAlias = ConfigField | Path | Sequence[Path] | ToolSettingsMap | ToolContextValue
ToolContextRawMapping: TypeAlias = Mapping[str, ToolContextPayloadValue | ToolContextExtras]
_EXTRA_KEY: Final[str] = "extra"


ParserField: TypeAlias = Parser | ParserLike | ParserContract | ParserImplementation | None


@runtime_checkable
class SupportsCommandBuild(Protocol):
    """Protocol describing objects that expose a ``build`` method returning command arguments."""

    def build(self, ctx: ToolContextProtocol) -> Sequence[str]:
        """Return command arguments for the provided execution context.

        Args:
            ctx: Tool execution context describing configuration and target files.

        Returns:
            Sequence[str]: Command arguments emitted by the builder.
        """

        raise NotImplementedError


CommandField: TypeAlias = CommandBuilder | CommandBuilderLike | CommandBuilderContract | SupportsCommandBuild


@runtime_checkable
class SupportsExecutionConfig(Protocol):
    """Protocol describing configuration objects exposing an ``execution`` attribute."""

    execution: ToolConfiguration
    """Execution configuration bundle associated with the configuration object."""


class ToolContext(BaseModel):
    """Runtime context made available when resolving tool commands."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cfg: ConfigField
    root: Path
    files: tuple[Path, ...] = Field(default_factory=tuple)
    settings: ToolSettingsMap = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _merge_extra(
        cls,
        data: ToolContextRawMapping,
    ) -> Mapping[str, ToolContextPayloadValue]:
        """Merge legacy ``extra`` payloads into the ToolContext mapping.

        Args:
            data: Raw payload supplied to the Pydantic model.

        Returns:
            Mapping[str, ToolContextPayloadValue]: Normalised payload ready for validation.

        Raises:
            TypeError: If ``data`` is not a mapping.
        """

        if not isinstance(data, Mapping):
            raise TypeError("ToolContext requires a mapping of field values")

        payload: dict[str, ToolContextPayloadValue] = {}
        extra_obj = data.get(_EXTRA_KEY)
        for key, value in data.items():
            if key == _EXTRA_KEY:
                continue
            payload[key] = cast(ToolContextPayloadValue, value)

        if isinstance(extra_obj, Mapping):
            for key, value in extra_obj.items():
                payload.setdefault(key, value)  # preserve explicit keyword arguments
        return payload

    @field_validator("cfg", mode="before")
    @classmethod
    def _coerce_cfg(cls, value: ConfigField | SupportsExecutionConfig) -> ConfigField:
        """Validate that the supplied configuration satisfies the expected contract.

        Args:
            value: Candidate configuration object provided by the caller.

        Returns:
            ConfigProtocol | ToolConfiguration: Configuration instance accepted by the context.

        Raises:
            TypeError: If the value does not implement the ``ToolConfiguration`` protocol.
        """

        if isinstance(value, ConfigProtocol):
            return value
        if isinstance(value, ToolConfiguration):
            return value
        if isinstance(value, SupportsExecutionConfig):
            return cast(ConfigProtocol, value)
        raise TypeError(
            "cfg must implement the pyqa.interfaces.config.Config protocol or ToolConfiguration",
        )

    @field_validator("files", mode="before")
    @classmethod
    def _coerce_files(
        cls,
        value: Sequence[Path | str] | Path | None,
    ) -> tuple[Path, ...]:
        """Normalise file collections into tuples of :class:`Path` instances.

        Args:
            value: Raw value supplied for the ``files`` field.

        Returns:
            tuple[Path, ...]: Files represented as ``Path`` objects.

        Raises:
            TypeError: If ``value`` is neither ``None`` nor a sequence of paths.
        """

        if value is None:
            return ()
        if isinstance(value, Path):
            return (value,)
        if isinstance(value, Sequence):
            return tuple(Path(item) if not isinstance(item, Path) else item for item in value)
        raise TypeError("files must be a sequence of paths")


class ActionExitCodes(BaseModel):
    """Categorise exit codes reported by a tool action.

    The orchestrator converts these collections into
    :class:`pyqa.core.models.ToolExitCategory` values so callers can distinguish
    between operational failures and diagnostics raised by the tool itself.
    """

    model_config = ConfigDict(validate_assignment=True)

    success: tuple[int, ...] = (0,)
    diagnostic: tuple[int, ...] = ()
    tool_failure: tuple[int, ...] = ()

    @field_validator("success", "diagnostic", "tool_failure", mode="before")
    @classmethod
    def _coerce_codes(
        cls,
        value: Sequence[int | str] | int | str | None,
    ) -> tuple[int, ...]:
        """Return validated integer exit codes from ``value``.

        Args:
            value: Raw exit code sequence supplied for a model field.

        Returns:
            tuple[int, ...]: Normalised integer exit codes.

        Raises:
            TypeError: If ``value`` is neither ``None`` nor an integer sequence.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(int(item) for item in value)
        if isinstance(value, (int, str)):
            return (int(value),)
        raise TypeError("exit code collections must contain integers")

    def as_sets(self) -> tuple[set[int], set[int], set[int]]:
        """Return success, diagnostic, and tool-failure codes as sets.

        Returns:
            tuple[set[int], set[int], set[int]]: Tuple containing the success,
            diagnostic, and tool-failure exit codes respectively.
        """

        return set(self.success), set(self.diagnostic), set(self.tool_failure)


class DeferredCommand(BaseModel):
    """Simple command builder that returns a fixed command list."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    args: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...]:
        """Return command arguments as a tuple of strings.

        Args:
            value: Raw argument value supplied to the model.

        Returns:
            tuple[str, ...]: Normalised command arguments.

        Raises:
            TypeError: If ``value`` is neither ``None`` nor string data.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("DeferredCommand args must be a sequence of strings")

    def __init__(
        self,
        args: Sequence[str] | None = None,
        extra: ToolContextExtras | None = None,
    ) -> None:
        """Initialise the deferred command with optional argument overrides.

        Args:
            args: Optional command-line arguments preserved for later use.
            extra: Additional key-value pairs forwarded to the Pydantic model to
                maintain compatibility with historical construction patterns.
        """

        payload: dict[str, ToolContextValue] = dict(extra or {})
        if args is not None:
            payload.setdefault("args", args)
        super().__init__(**payload)

    def build(self, ctx: ToolContextProtocol) -> Sequence[str]:
        """Return the deferred command regardless of the provided context.

        Args:
            ctx: Tool execution context; unused for deferred commands.

        Returns:
            Sequence[str]: Command arguments captured during construction.
        """

        del ctx
        return tuple(self.args)

    def describe(self) -> str:
        """Return a human-readable description of the deferred command.

        Returns:
            str: Static identifier representing the deferred command.
        """

        return "DeferredCommand"

    def __call__(self, ctx: ToolContextProtocol) -> Sequence[str]:
        """Support call-style invocation mirroring :meth:`build`.

        Args:
            ctx: Tool execution context; unused for deferred commands.

        Returns:
            Sequence[str]: Command arguments captured during construction.
        """

        return self.build(ctx)


class ToolAction(BaseModel):
    """Single executable action belonging to a tool (e.g. lint, fix)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    command: CommandField
    is_fix: bool = False
    append_files: bool = True
    filter_patterns: tuple[str, ...] = Field(default_factory=tuple)
    ignore_exit: bool = False
    description: str = ""
    timeout_s: float | None = None
    env: Mapping[str, str] = Field(default_factory=dict)
    parser: ParserField = None
    exit_codes: ActionExitCodes = Field(default_factory=ActionExitCodes)
    internal_runner: InternalActionRunner | None = None

    @field_validator("command", mode="before")
    @classmethod
    def _coerce_command(cls, value: CommandField | SupportsCommandBuild) -> CommandField:
        """Validate that command builders expose the required interface.

        Args:
            value: Candidate command builder supplied for the action.

        Returns:
            CommandBuilder: Accepted command builder instance.

        Raises:
            TypeError: If the value does not provide a ``build`` method.
        """

        if isinstance(value, CommandBuilder):
            return value
        if isinstance(value, CommandBuilderLike):
            return value
        if isinstance(value, CommandBuilderContract):
            return value
        if isinstance(value, SupportsCommandBuild):
            return cast(CommandBuilderContract, value)
        raise TypeError("command must provide a callable 'build' method")

    @field_validator("parser", mode="before")
    @classmethod
    def _coerce_parser(
        cls,
        value: Parser | ParserLike | ParserContract | ParserImplementation | None,
    ) -> ParserField:
        """Validate parser instances supplied for tool actions.

        Args:
            value: Candidate parser supplied for diagnostic extraction.

        Returns:
            ParserLike | None: Accepted parser instance.

        Raises:
            TypeError: If the value does not satisfy the ``Parser`` protocol.
        """

        if value is None:
            return None
        if isinstance(value, (Parser, ParserLike, ParserContract, ParserImplementation)):
            return cast(ParserField, value)
        if _supports_parser_interface(value):
            return cast(ParserField, value)
        raise TypeError("parser must implement the Parser protocol")

    @field_validator("filter_patterns", mode="before")
    @classmethod
    def _coerce_patterns(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...]:
        """Return tuple of glob patterns parsed from ``value``.

        Args:
            value: Raw pattern specification.

        Returns:
            tuple[str, ...]: Normalised glob or regex patterns.

        Raises:
            TypeError: If ``value`` does not contain string data.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("filter_patterns must be a sequence of strings")

    @field_validator("env", mode="before")
    @classmethod
    def _coerce_env(
        cls,
        value: Mapping[str, str | int | float | bool | Path] | None,
    ) -> Mapping[str, str]:
        """Return validated environment mappings for an action.

        Args:
            value: Raw environment mapping supplied to the model.

        Returns:
            Mapping[str, str]: Environment variables expressed as strings.

        Raises:
            TypeError: If ``value`` is neither ``None`` nor a mapping.
        """

        if value is None:
            return {}
        if isinstance(value, Mapping):
            return {str(k): str(v) for k, v in value.items()}
        raise TypeError("env must be a mapping of strings")

    @field_validator("internal_runner", mode="before")
    @classmethod
    def _coerce_internal_runner(
        cls,
        value: InternalActionRunner | None,
    ) -> InternalActionRunner | None:
        """Validate optional internal runner callbacks.

        Args:
            value: Candidate callable supplied for the ``internal_runner`` field.

        Returns:
            InternalActionRunner | None: Runner preserved when valid, otherwise
            ``None`` when unset.

        Raises:
            TypeError: If ``value`` is not callable.
        """

        if value is None:
            return None
        if isinstance(value, InternalActionRunner):
            return value
        raise TypeError("internal_runner must be callable")

    def build_command(self, ctx: ToolContextProtocol) -> list[str]:
        """Return the command arguments for this action within ``ctx``.

        Args:
            ctx: Tool execution context containing configuration and file selections.

        Returns:
            list[str]: Command arguments including optional file parameters.
        """

        cmd = list(self.command.build(ctx))
        if self.append_files and ctx.files:
            cmd.extend(str(path) for path in ctx.files)
        return cmd

    @property
    def is_internal(self) -> bool:
        """Return ``True`` when the action executes via an internal runner.

        Returns:
            bool: ``True`` when :attr:`internal_runner` is configured.
        """

        return self.internal_runner is not None

    def filter_stdout(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Filter stdout text using configured patterns and ``extra_patterns``.

        Args:
            text: Raw stdout string emitted by the tool.
            extra_patterns: Optional glob or regex patterns applied in addition to
                the action's configured filters.

        Returns:
            str: Filtered stdout text with matching patterns removed.
        """

        return self._apply_filters(text, extra_patterns)

    def filter_stderr(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Filter stderr text using configured patterns and ``extra_patterns``.

        Args:
            text: Raw stderr string emitted by the tool.
            extra_patterns: Optional glob or regex patterns applied in addition to
                the action's configured filters.

        Returns:
            str: Filtered stderr text with matching patterns removed.
        """

        return self._apply_filters(text, extra_patterns)

    def _apply_filters(self, text: str, extra_patterns: Sequence[str] | None) -> str:
        """Apply output filtering for the action and return the filtered text.

        Args:
            text: Output string to filter.
            extra_patterns: Additional patterns layered on top of :attr:`filter_patterns`.

        Returns:
            str: Filtered output string.
        """

        patterns = list(self.filter_patterns)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return OutputFilter(patterns=tuple(patterns)).apply(text)


class ToolDocumentationEntry(BaseModel):
    """Documentation snippet captured for help surfaces."""

    format: str = "text"
    content: str


PHASE_NAMES: Final[tuple[str, ...]] = (
    "format",
    "lint",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)

PhaseLiteral = Literal[
    "lint",
    "format",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
]


class ToolDocumentation(BaseModel):
    """Grouped documentation entries for a tool."""

    help: ToolDocumentationEntry | None = None
    command: ToolDocumentationEntry | None = None
    shared: ToolDocumentationEntry | None = None


class Tool(BaseModel):
    """Description of a lint tool composed of multiple actions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    actions: tuple[ToolAction, ...]
    phase: PhaseLiteral = "lint"
    before: tuple[str, ...] = Field(default_factory=tuple)
    after: tuple[str, ...] = Field(default_factory=tuple)
    languages: tuple[str, ...] = Field(default_factory=tuple)
    file_extensions: tuple[str, ...] = Field(default_factory=tuple)
    config_files: tuple[str, ...] = Field(default_factory=tuple)
    description: str = ""
    tags: tuple[str, ...] = Field(default_factory=tuple)
    auto_install: bool = False
    default_enabled: bool = True
    automatically_fix: bool = True
    runtime: Literal["python", "npm", "binary", "go", "lua", "perl", "rust"] = "python"
    package: str | None = None
    min_version: str | None = None
    prefer_local: bool = False
    version_command: tuple[str, ...] | None = None
    suppressions_tests: tuple[str, ...] = Field(default_factory=tuple)
    suppressions_general: tuple[str, ...] = Field(default_factory=tuple)
    suppressions_duplicates: tuple[str, ...] = Field(default_factory=tuple)
    installers: tuple[InstallerCallable, ...] = Field(default_factory=tuple)
    documentation: ToolDocumentation | None = None

    _actions_by_name: dict[str, ToolAction] = PrivateAttr(default_factory=dict)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(
        cls,
        value: ToolAction | Iterable[ToolAction],
    ) -> tuple[ToolAction, ...]:
        """Normalise tool actions into tuples for deterministic ordering.

        Args:
            value: Raw action or iterable supplied for the ``actions`` field.

        Returns:
            tuple[ToolAction, ...]: Tuple containing validated actions.

        Raises:
            TypeError: If ``value`` contains non-``ToolAction`` members.
        """

        if isinstance(value, ToolAction):
            return (value,)
        if isinstance(value, Iterable):
            items: list[ToolAction] = []
            for item in value:
                if not isinstance(item, ToolAction):
                    raise TypeError("actions must contain ToolAction instances")
                items.append(item)
            return tuple(items)
        raise TypeError("actions must be an iterable of ToolAction instances")

    @model_validator(mode="after")
    def _populate_action_index(self) -> Tool:
        """Populate the private action index after validation completes.

        Returns:
            Tool: Instance with refreshed action index for fluent chaining.
        """

        self._refresh_action_index()
        return self

    def _refresh_action_index(self) -> None:
        """Rebuild the name -> action index for quick lookups."""

        object.__setattr__(
            self,
            "_actions_by_name",
            {action.name: action for action in self.actions},
        )

    def __len__(self) -> int:
        """Return the number of actions associated with the tool.

        Returns:
            int: Count of actions defined on this tool.
        """

        return len(self.actions)

    def __contains__(self, item: ToolAction | str) -> bool:
        """Return whether ``item`` refers to an action in this tool.

        Args:
            item: Tool action instance or action name.

        Returns:
            bool: ``True`` when the action exists on this tool.
        """

        if isinstance(item, ToolAction):
            return item in self.actions
        return isinstance(item, str) and item in self._actions_by_name

    def __getitem__(self, key: int | str) -> ToolAction:
        """Return the action identified by ``key``.

        Args:
            key: Action index or action name.

        Returns:
            ToolAction: Action associated with ``key``.

        Raises:
            TypeError: If ``key`` is neither an ``int`` nor ``str``.
        """

        if isinstance(key, int):
            return self.actions[key]
        if isinstance(key, str):
            return self._actions_by_name[key]
        raise TypeError("Tool indices must be integers or action names")

    def keys(self) -> Iterable[str]:
        """Return an iterable over the action names managed by the tool.

        Returns:
            Iterable[str]: Iterable producing action names.
        """

        return self._actions_by_name.keys()

    def values(self) -> Iterable[ToolAction]:
        """Return an iterable over the tool actions.

        Returns:
            Iterable[ToolAction]: Iterable yielding tool actions.
        """

        return self._actions_by_name.values()

    def items(self) -> Iterable[tuple[str, ToolAction]]:
        """Return ``(name, action)`` pairs for all actions.

        Returns:
            Iterable[tuple[str, ToolAction]]: Iterable yielding action name/action pairs.
        """

        return self._actions_by_name.items()

    def get(self, name: str, default: ToolAction | None = None) -> ToolAction | None:
        """Return the action identified by ``name``.

        Args:
            name: Action name to resolve.
            default: Fallback action returned when ``name`` is unknown.

        Returns:
            ToolAction | None: Matching action or ``default`` when not found.
        """

        return self._actions_by_name.get(name, default)

    def action_names(self) -> tuple[str, ...]:
        """Return the tuple of action names in declaration order.

        Returns:
            tuple[str, ...]: Action names preserving declaration order.
        """

        return tuple(self._actions_by_name.keys())

    def iter_actions(self) -> Iterator[ToolAction]:
        """Return an iterator over actions preserving declaration order.

        Returns:
            Iterator[ToolAction]: Iterator traversing the configured actions.
        """

        return iter(self.actions)

    @field_validator("languages", "file_extensions", "config_files", mode="before")
    @classmethod
    def _coerce_str_tuple(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...]:
        """Return tuple of strings parsed from a field value.

        Args:
            value: Raw value supplied for tuple fields.

        Returns:
            tuple[str, ...]: Normalised tuple of strings.

        Raises:
            TypeError: If ``value`` does not contain strings.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("expected a sequence of strings")

    @field_validator("before", "after", mode="before")
    @classmethod
    def _coerce_ordering(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...]:
        """Validate ordering constraints attached to a tool.

        Args:
            value: Sequence describing ordering relationships.

        Returns:
            tuple[str, ...]: Normalised ordering entries.

        Raises:
            TypeError: If ``value`` does not contain string data.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("expected a sequence of strings")

    @field_validator("version_command", mode="before")
    @classmethod
    def _coerce_version_cmd(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...] | None:
        """Validate the optional command used to resolve tool versions.

        Args:
            value: Raw command specification supplied via configuration.

        Returns:
            tuple[str, ...] | None: Normalised command arguments or ``None`` when
            no custom command is configured.

        Raises:
            TypeError: If ``value`` does not contain string data.
        """

        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("version_command must be a sequence of strings or None")

    @field_validator(
        "suppressions_tests",
        "suppressions_general",
        "suppressions_duplicates",
        mode="before",
    )
    @classmethod
    def _coerce_suppressions(
        cls,
        value: Sequence[str] | str | None,
    ) -> tuple[str, ...]:
        """Validate suppression identifiers for a tool.

        Args:
            value: Raw suppression identifiers supplied via configuration.

        Returns:
            tuple[str, ...]: Normalised suppression identifiers.

        Raises:
            TypeError: If ``value`` does not contain string data.
        """

        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("suppression entries must be strings")

    @field_validator("installers", mode="before")
    @classmethod
    def _coerce_installers(
        cls,
        value: Sequence[InstallerCallable] | InstallerCallable | None,
    ) -> tuple[InstallerCallable, ...]:
        """Validate optional installer callback sequences.

        Args:
            value: Raw installer callable or sequence of callables.

        Returns:
            tuple[InstallerCallable, ...]: Normalised installer callbacks.

        Raises:
            TypeError: If ``value`` contains non-callable members.
        """

        if value is None:
            return ()
        if isinstance(value, tuple):
            return tuple(cls._require_installer(item) for item in value)
        if isinstance(value, list):
            return tuple(cls._require_installer(item) for item in value)
        if isinstance(value, InstallerCallable):
            return (value,)
        raise TypeError("installers must be a sequence of callables")

    @staticmethod
    def _require_installer(candidate: InstallerCallable) -> InstallerCallable:
        """Return ``candidate`` when it satisfies the :class:`InstallerCallable` protocol.

        Args:
            candidate: Installer callable being validated.

        Returns:
            InstallerCallable: Validated installer callable.

        Raises:
            TypeError: If ``candidate`` does not implement :class:`InstallerCallable`.
        """

        if not isinstance(candidate, InstallerCallable):
            raise TypeError("installers must contain callables")
        return candidate

    def is_applicable(
        self,
        *,
        language: str | None = None,
        files: Sequence[Path] | None = None,
    ) -> bool:
        """Return whether the tool applies to the supplied ``language``/``files`` selection.

        Args:
            language: Language identifier associated with the invocation.
            files: Candidate files that may be passed to the tool.

        Returns:
            bool: ``True`` when the tool should run with the supplied parameters.
        """

        if language and self.languages and language not in self.languages:
            return False
        if files:
            allowed = {ext.lower() for ext in self.file_extensions}
            if allowed and not any(path.suffix.lower() in allowed for path in files):
                return False
        return True


ToolContext.model_rebuild(_types_namespace={"JSONValue": _CatalogJSONValue})
def _supports_parser_interface(candidate: object) -> bool:
    """Return ``True`` when ``candidate`` exposes a ``parse`` method."""

    parse = getattr(candidate, "parse", None)
    return callable(parse)
