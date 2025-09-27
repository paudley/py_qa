# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Definitions for lint tools and their actions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from pyqa.models import Diagnostic, OutputFilter, RawDiagnostic

if TYPE_CHECKING:
    from pyqa.config import Config


class ToolContext(BaseModel):
    """Runtime context made available when resolving tool commands."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cfg: ConfigField
    root: Path
    files: tuple[Path, ...] = Field(default_factory=tuple)
    settings: Mapping[str, object] = Field(default_factory=dict)

    def __init__(
        self,
        *,
        cfg: ConfigField,
        root: Path,
        files: Sequence[Path] | None = None,
        settings: Mapping[str, object] | None = None,
        **extra: object,
    ) -> None:
        """Initialise the context with optional file and settings overrides."""
        payload: dict[str, object] = dict(extra)
        if files is not None:
            payload.setdefault("files", files)
        if settings is not None:
            payload.setdefault("settings", settings)
        super().__init__(cfg=cfg, root=root, **payload)

    @field_validator("files", mode="before")
    @classmethod
    def _coerce_files(cls, value: object) -> tuple[Path, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, Sequence):
            return tuple(Path(item) if not isinstance(item, Path) else item for item in value)
        message = "ToolContext.files must be a sequence of paths"
        raise TypeError(message)


class Parser(Protocol):
    """Protocol implemented by output parsers."""

    def parse(
        self,
        stdout: str,
        stderr: str,
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Convert raw tool output into diagnostics or raw diagnostics."""
        raise NotImplementedError


class CommandBuilder(Protocol):
    """Build a command for execution based on the tool context."""

    def build(self, ctx: ToolContext) -> Sequence[str]: ...


if TYPE_CHECKING:
    CommandField = CommandBuilder
    ParserField = Parser | None
    ConfigField = Config
else:
    CommandField = object
    ParserField = object
    ConfigField = object


class DeferredCommand(BaseModel):
    """Simple command builder that returns a fixed command list."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    args: tuple[str, ...]

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        message = "DeferredCommand args must be a sequence of strings"
        raise TypeError(message)

    def __init__(self, args: Sequence[str] | None = None, **extra: object) -> None:
        """Initialise the deferred command with an optional argument sequence."""
        payload: dict[str, object] = dict(extra)
        if args is not None:
            payload.setdefault("args", args)
        super().__init__(**payload)

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the stored command ignoring the provided context."""
        del ctx
        return tuple(self.args)


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

    @field_validator("filter_patterns", mode="before")
    @classmethod
    def _coerce_patterns(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        message = "filter_patterns must be a sequence of strings"
        raise TypeError(message)

    @field_validator("env", mode="before")
    @classmethod
    def _coerce_env(cls, value: object) -> Mapping[str, str]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return {str(k): str(v) for k, v in value.items()}
        message = "env must be a mapping of strings"
        raise TypeError(message)

    def build_command(self, ctx: ToolContext) -> list[str]:
        """Construct the command for this action using the given context."""
        cmd = list(self.command.build(ctx))
        if self.append_files and ctx.files:
            cmd.extend(str(path) for path in ctx.files)
        return cmd

    def filter_stdout(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Apply action-specific stdout filters plus any extra patterns."""
        patterns = list(self.filter_patterns)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return OutputFilter(patterns=tuple(patterns)).apply(text)

    def filter_stderr(self, text: str, extra_patterns: Sequence[str] | None = None) -> str:
        """Apply action-specific stderr filters plus any extra patterns."""
        patterns = list(self.filter_patterns)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return OutputFilter(patterns=tuple(patterns)).apply(text)


class Tool(BaseModel):
    """Description of a lint tool composed of multiple actions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    actions: tuple[ToolAction, ...]
    languages: tuple[str, ...] = Field(default_factory=tuple)
    file_extensions: tuple[str, ...] = Field(default_factory=tuple)
    config_files: tuple[str, ...] = Field(default_factory=tuple)
    description: str = ""
    auto_install: bool = False
    default_enabled: bool = True
    runtime: Literal["python", "npm", "binary", "go", "lua", "perl", "rust"] = "python"
    package: str | None = None
    min_version: str | None = None
    prefer_local: bool = False
    version_command: tuple[str, ...] | None = None

    _actions_by_name: dict[str, ToolAction] = PrivateAttr(default_factory=dict)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> tuple[ToolAction, ...]:
        if isinstance(value, ToolAction):
            return (value,)
        if isinstance(value, Iterable):
            items: list[ToolAction] = []
            for item in value:
                if not isinstance(item, ToolAction):
                    message = "actions must contain ToolAction instances"
                    raise TypeError(message)
                items.append(item)
            return tuple(items)
        message = "actions must be an iterable of ToolAction instances"
        raise TypeError(message)

    def model_post_init(self, __context: object) -> None:  # pragma: no cover - pydantic hook
        """Populate auxiliary lookup structures after model construction."""
        self._refresh_action_index()

    def _refresh_action_index(self) -> None:
        object.__setattr__(
            self,
            "_actions_by_name",
            {action.name: action for action in self.actions},
        )

    def __iter__(self) -> Iterator[tuple[str, ToolAction]]:
        """Iterate over ``(name, action)`` pairs for this tool."""
        return iter(self._actions_by_name.items())

    def __len__(self) -> int:
        """Return the number of configured actions."""
        return len(self.actions)

    def __contains__(self, item: object) -> bool:
        """Return ``True`` when *item* refers to one of the tool actions."""
        if isinstance(item, ToolAction):
            return item in self.actions
        if isinstance(item, str):
            return item in self._actions_by_name
        return False

    def __getitem__(self, key: int | str) -> ToolAction:
        """Access an action by positional index or by name."""
        if isinstance(key, int):
            return self.actions[key]
        if isinstance(key, str):
            return self._actions_by_name[key]
        message = "Tool indices must be integers or action names"
        raise TypeError(message)

    def keys(self) -> Iterable[str]:
        """Return an iterable of action names."""
        return self._actions_by_name.keys()

    def values(self) -> Iterable[ToolAction]:
        """Return an iterable over configured actions."""
        return self._actions_by_name.values()

    def items(self) -> Iterable[tuple[str, ToolAction]]:
        """Return ``(name, action)`` tuples for every configured action."""
        return self._actions_by_name.items()

    def get(self, name: str, default: ToolAction | None = None) -> ToolAction | None:
        """Return an action by *name* or *default* when absent."""
        return self._actions_by_name.get(name, default)

    def action_names(self) -> tuple[str, ...]:
        """Return the ordered tuple of action names."""
        return tuple(self._actions_by_name.keys())

    @field_validator("languages", "file_extensions", "config_files", mode="before")
    @classmethod
    def _coerce_str_tuple(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        message = "expected a sequence of strings"
        raise TypeError(message)

    @field_validator("version_command", mode="before")
    @classmethod
    def _coerce_version_cmd(cls, value: object) -> tuple[str, ...] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value)
        if isinstance(value, str):
            return (value,)
        message = "version_command must be a sequence of strings or None"
        raise TypeError(message)

    def is_applicable(
        self,
        *,
        language: str | None = None,
        files: Sequence[Path] | None = None,
    ) -> bool:
        """Return ``True`` when the tool should run for the given inputs."""
        if language and self.languages and language not in self.languages:
            return False
        if files:
            allowed = {ext.lower() for ext in self.file_extensions}
            if allowed and not any(path.suffix.lower() in allowed for path in files):
                return False
        return True
