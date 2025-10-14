# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Definitions for lint tools and their actions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from ..config.types import ConfigValue
from ..core.models import Diagnostic, OutputFilter, RawDiagnostic, ToolOutcome

ToolSettingsMap: TypeAlias = Mapping[str, ConfigValue]
ToolContextValue: TypeAlias = ConfigValue | Sequence[Path]
ToolContextExtras: TypeAlias = Mapping[str, ToolContextValue]


@runtime_checkable
class Parser(Protocol):
    """Protocol implemented by output parsers."""

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Convert raw tool output into diagnostics or raw diagnostics."""
        raise NotImplementedError


@runtime_checkable
class CommandBuilder(Protocol):
    """Build a command for execution based on the tool context."""

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the executable command derived from *ctx*."""
        raise NotImplementedError


if TYPE_CHECKING:
    from ..config import Config

    ConfigField = Config
else:

    @runtime_checkable
    class _ConfigProtocol(Protocol):
        """Runtime placeholder satisfied by configuration models."""

        ...

    ConfigField = _ConfigProtocol

CommandField: TypeAlias = CommandBuilder
ParserField: TypeAlias = Parser | None


class ToolContext(BaseModel):
    """Runtime context made available when resolving tool commands."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cfg: ConfigField
    root: Path
    files: tuple[Path, ...] = Field(default_factory=tuple)
    settings: ToolSettingsMap = Field(default_factory=dict)

    # suppression_valid: lint=internal-signatures context initializer mirrors historical call signature so tool integrations can pass arbitrary metadata without wrapper shims.
    def __init__(
        self,
        *,
        cfg: ConfigField,
        root: Path,
        files: Sequence[Path] | None = None,
        settings: ToolSettingsMap | None = None,
        extra: ToolContextExtras | None = None,
    ) -> None:
        """Initialise a tool context used during command construction.

        Args:
            cfg: Active configuration model for the invocation.
            root: Project root directory associated with the run.
            files: Optional sequence of files selected for the tool.
            settings: Tool-specific configuration overrides.
            extra: Optional mapping of additional attributes carried forward for
                compatibility with historical call sites.
        """

        payload: dict[str, ToolContextValue] = dict(extra or {})
        if files is not None:
            payload.setdefault("files", files)
        if settings is not None:
            payload.setdefault("settings", settings)
        super().__init__(cfg=cfg, root=root, **payload)

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


@runtime_checkable
class InstallerCallable(Protocol):
    """Protocol implemented by installer callbacks."""

    def __call__(self, ctx: ToolContext) -> None:
        """Perform installation steps for the tool using *ctx*."""

        ...


@runtime_checkable
class InternalActionRunner(Protocol):
    """Protocol implemented by internal tool action runners."""

    def __call__(self, ctx: ToolContext) -> ToolOutcome:
        """Execute the action and return a :class:`ToolOutcome`."""

        ...


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
        """Return success, diagnostic, and tool-failure codes as sets."""

        return set(self.success), set(self.diagnostic), set(self.tool_failure)


class DeferredCommand(BaseModel):
    """Simple command builder that returns a fixed command list."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    args: tuple[str, ...]

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

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the deferred command regardless of the provided *ctx*."""

        del ctx
        return tuple(self.args)

    def describe(self) -> str:
        """Return a human-readable description of the deferred command."""

        return "DeferredCommand"


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

    def build_command(self, ctx: ToolContext) -> list[str]:
        """Return the command arguments for this action within *ctx*."""

        cmd = list(self.command.build(ctx))
        if self.append_files and ctx.files:
            cmd.extend(str(path) for path in ctx.files)
        return cmd

    @property
    def is_internal(self) -> bool:
        """Return ``True`` when the action executes via an internal runner."""

        return self.internal_runner is not None

    def filter_stdout(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Filter stdout text using configured patterns and *extra_patterns*."""

        return self._apply_filters(text, extra_patterns)

    def filter_stderr(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Filter stderr text using configured patterns and *extra_patterns*."""

        return self._apply_filters(text, extra_patterns)

    def _apply_filters(self, text: str, extra_patterns: Sequence[str] | None) -> str:
        """Apply output filtering for the action and return the filtered text."""

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
        """Populate the private action index after validation completes."""

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
        """Return the number of actions associated with the tool."""

        return len(self.actions)

    def __contains__(self, item: ToolAction | str) -> bool:
        """Return ``True`` when *item* refers to an action in this tool."""

        if isinstance(item, ToolAction):
            return item in self.actions
        return isinstance(item, str) and item in self._actions_by_name

    def __getitem__(self, key: int | str) -> ToolAction:
        if isinstance(key, int):
            return self.actions[key]
        if isinstance(key, str):
            return self._actions_by_name[key]
        raise TypeError("Tool indices must be integers or action names")

    def keys(self) -> Iterable[str]:
        """Return an iterable over the action names managed by the tool."""

        return self._actions_by_name.keys()

    def values(self) -> Iterable[ToolAction]:
        """Return an iterable over the tool actions."""

        return self._actions_by_name.values()

    def items(self) -> Iterable[tuple[str, ToolAction]]:
        """Return (name, action) pairs for all actions."""

        return self._actions_by_name.items()

    def get(self, name: str, default: ToolAction | None = None) -> ToolAction | None:
        """Return the action identified by *name*, falling back to *default*."""

        return self._actions_by_name.get(name, default)

    def action_names(self) -> tuple[str, ...]:
        """Return the tuple of action names in declaration order."""

        return tuple(self._actions_by_name.keys())

    def iter_actions(self) -> Iterator[ToolAction]:
        """Return an iterator over actions preserving declaration order."""

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
        """Return ``candidate`` when it satisfies the :class:`InstallerCallable` protocol."""

        if not isinstance(candidate, InstallerCallable):
            raise TypeError("installers must contain callables")
        return candidate

    def is_applicable(
        self,
        *,
        language: str | None = None,
        files: Sequence[Path] | None = None,
    ) -> bool:
        """Return ``True`` when the tool is applicable to *language*/*files*."""

        if language and self.languages and language not in self.languages:
            return False
        if files:
            allowed = {ext.lower() for ext in self.file_extensions}
            if allowed and not any(path.suffix.lower() in allowed for path in files):
                return False
        return True
