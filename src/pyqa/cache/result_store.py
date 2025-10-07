# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Simple file-based caching for tool outcomes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from ..core.metrics import FileMetrics
from ..core.models import ToolOutcome
from ..core.serialization import deserialize_outcome, safe_int, serialize_outcome

COMMAND_DELIMITER: Final[bytes] = b"::"
FILES_FIELD: Final[Literal["files"]] = "files"
FILE_METRICS_FIELD: Final[Literal["file_metrics"]] = "file_metrics"
PATH_FIELD: Final[Literal["path"]] = "path"
MTIME_FIELD: Final[Literal["mtime_ns"]] = "mtime_ns"
SIZE_FIELD: Final[Literal["size"]] = "size"


class StatePayload(TypedDict, total=False):
    """Serialized file state captured in the cache payload."""

    path: str
    mtime_ns: int
    size: int


class MetricPayload(TypedDict, total=False):
    """Serialized file metrics stored in the cache payload."""

    path: str
    line_count: int
    suppressions: dict[str, int]


@dataclass(frozen=True, slots=True)
class CacheRequest:
    """Normalized inputs that identify a cached command outcome."""

    tool: str
    action: str
    command: tuple[str, ...]
    files: tuple[Path, ...]
    token: str


@dataclass(frozen=True, slots=True)
class CachedEntry:
    """Cached outcome and associated metrics retrieved from disk."""

    outcome: ToolOutcome
    file_metrics: dict[str, FileMetrics]


class _CacheMiss(Exception):
    """Raised when a cache entry cannot be used for the current inputs."""


class FileState(BaseModel):
    """Filesystem metadata used to validate cache entries."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    path: Path
    mtime_ns: int
    size: int


def _collect_file_states(files: Sequence[Path]) -> tuple[FileState, ...]:
    """Return the filesystem state for *files*, or an empty tuple if missing.

    Args:
        files: Files whose metadata should be captured.

    Returns:
        tuple[FileState, ...]: Recorded metadata for each file, or ``()`` when
        any file is missing.
    """

    states: list[FileState] = []
    for path in files:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return ()
        states.append(
            FileState(
                path=path.resolve(),
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
            ),
        )
    return tuple(states)


def _validate_state_match(
    current_states: tuple[FileState, ...],
    stored_states: tuple[StatePayload, ...],
) -> None:
    """Ensure the cached file states match the current filesystem state.

    Args:
        current_states: Fresh filesystem metadata for the files under
            consideration.
        stored_states: Serialized state payload recovered from the cache entry.

    Raises:
        _CacheMiss: If the current filesystem state no longer matches the
        stored metadata.
    """

    if len(current_states) != len(stored_states):
        raise _CacheMiss
    stored_by_path = {payload[PATH_FIELD]: payload for payload in stored_states if PATH_FIELD in payload}
    if len(stored_by_path) != len(stored_states):
        raise _CacheMiss

    for state in current_states:
        payload = stored_by_path.get(str(state.path))
        if payload is None:
            raise _CacheMiss
        stored_mtime = payload.get(MTIME_FIELD)
        stored_size = payload.get(SIZE_FIELD)
        if stored_mtime is None or safe_int(stored_mtime) != state.mtime_ns:
            raise _CacheMiss
        if stored_size is None or safe_int(stored_size) != state.size:
            raise _CacheMiss


def _state_to_payload(state: FileState) -> StatePayload:
    """Convert a :class:`FileState` into its serialized representation.

    Args:
        state: File metadata snapshot gathered at cache time.

    Returns:
        StatePayload: JSON-serializable payload describing ``state``.
    """

    return StatePayload(
        path=str(state.path),
        mtime_ns=state.mtime_ns,
        size=state.size,
    )


class ResultCache:
    """Persist tool outcomes to disk and reload them when inputs are unchanged."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def load(self, request: CacheRequest) -> CachedEntry | None:
        """Return the cached entry for *request* when inputs still match.

        Args:
            request: Cache request describing the tool invocation to resolve.

        Returns:
            CachedEntry | None: Cached outcome when the filesystem matches, or
            ``None`` when the entry is missing or stale.
        """

        entry_path = self._entry_path(request)
        if not entry_path.is_file():
            return None
        try:
            payload = self._read_entry(entry_path)
        except _CacheMiss:
            return None

        current_states = _collect_file_states(request.files)
        if not _files_available(request.files, current_states):
            return None
        stored_states = _coerce_state_payload(payload.get(FILES_FIELD))
        if not _states_match(current_states, stored_states):
            return None

        outcome = deserialize_outcome(payload)
        outcome.cached = True
        metrics = _coerce_metrics_payload(payload.get(FILE_METRICS_FIELD))
        return CachedEntry(outcome=outcome, file_metrics=metrics)

    def store(
        self,
        request: CacheRequest,
        *,
        outcome: ToolOutcome,
        file_metrics: Mapping[str, FileMetrics] | None = None,
    ) -> None:
        """Persist *outcome* for *request*, ignoring disk errors.

        Args:
            request: Cache request describing the tool invocation.
            outcome: Outcome object to serialize and persist.
            file_metrics: Optional metrics associated with the outcome.
        """

        self._dir.mkdir(parents=True, exist_ok=True)
        entry_path = self._entry_path(request)
        states = _collect_file_states(request.files)
        if not _files_available(request.files, states):
            return

        payload = _outcome_to_payload(outcome, states, file_metrics or {})
        try:
            entry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Cache writes are best-effort; ignore disk errors.
            return

    def _entry_path(self, request: CacheRequest) -> Path:
        hasher = hashlib.sha256()
        hasher.update(request.tool.encode("utf-8"))
        hasher.update(COMMAND_DELIMITER)
        hasher.update(request.action.encode("utf-8"))
        hasher.update(COMMAND_DELIMITER)
        hasher.update("\0".join(request.command).encode("utf-8"))
        hasher.update(COMMAND_DELIMITER)
        hasher.update(request.token.encode("utf-8"))
        digest = hasher.hexdigest()
        return self._dir / f"{digest}.json"

    def _read_entry(self, entry_path: Path) -> dict[str, object]:
        """Return the parsed JSON payload for *entry_path* or raise cache miss.

        Args:
            entry_path: Cache file location to read.

        Returns:
            dict[str, object]: Parsed JSON payload.

        Raises:
            _CacheMiss: If the file cannot be read or does not contain a JSON
            object.
        """

        try:
            raw = json.loads(entry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - OS failures
            raise _CacheMiss from exc
        if not isinstance(raw, dict):
            raise _CacheMiss
        return raw


def _files_available(files: Sequence[Path], states: tuple[FileState, ...]) -> bool:
    """Return ``True`` when all requested files were successfully stat'ed."""

    return not files or bool(states)


def _states_match(
    current_states: tuple[FileState, ...],
    stored_states: tuple[StatePayload, ...],
) -> bool:
    """Return ``True`` when ``stored_states`` matches ``current_states``."""

    if len(current_states) != len(stored_states):
        return False
    stored_by_path = {payload[PATH_FIELD]: payload for payload in stored_states if PATH_FIELD in payload}
    if len(stored_by_path) != len(stored_states):
        return False

    for state in current_states:
        payload = stored_by_path.get(str(state.path))
        if payload is None:
            return False
        stored_mtime = payload.get(MTIME_FIELD)
        stored_size = payload.get(SIZE_FIELD)
        if stored_mtime is None or safe_int(stored_mtime) != state.mtime_ns:
            return False
        if stored_size is None or safe_int(stored_size) != state.size:
            return False
    return True


def _outcome_to_payload(
    outcome: ToolOutcome,
    states: Iterable[FileState],
    file_metrics: Mapping[str, FileMetrics],
) -> dict[str, object]:
    payload = serialize_outcome(outcome)
    payload[FILES_FIELD] = [_state_to_payload(state) for state in states]
    if file_metrics:
        payload[FILE_METRICS_FIELD] = _metrics_to_payload(file_metrics)
    return payload


def _coerce_state_payload(value: object) -> tuple[StatePayload, ...]:
    """Return normalized state payloads extracted from *value*.

    Args:
        value: Raw JSON value recovered from the cache payload.

    Returns:
        tuple[StatePayload, ...]: Validated and normalized state payloads.
    """

    if not isinstance(value, list):
        return ()
    states: list[StatePayload] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path_value = item.get(PATH_FIELD)
        if not isinstance(path_value, str):
            continue
        payload: StatePayload = {PATH_FIELD: path_value}
        if MTIME_FIELD in item:
            payload[MTIME_FIELD] = safe_int(item[MTIME_FIELD])
        if SIZE_FIELD in item:
            payload[SIZE_FIELD] = safe_int(item[SIZE_FIELD])
        states.append(payload)
    return tuple(states)


def _metrics_to_payload(metrics: Mapping[str, FileMetrics]) -> list[MetricPayload]:
    """Return serialized payload for ``file_metrics`` persistence.

    Args:
        metrics: Derived file metrics keyed by normalized path.

    Returns:
        list[MetricPayload]: JSON-serializable payload describing ``metrics``.
    """

    entries: list[MetricPayload] = []
    for path_str, metric in metrics.items():
        entries.append(
            MetricPayload(
                path=path_str,
                line_count=metric.line_count,
                suppressions=dict(metric.suppressions),
            ),
        )
    return entries


def _coerce_metrics_payload(value: object) -> dict[str, FileMetrics]:
    """Return ``FileMetrics`` instances recreated from serialized payload.

    Args:
        value: Raw JSON value recovered from the cache payload.

    Returns:
        dict[str, FileMetrics]: Mapping of normalized paths to metric objects.
    """

    if not isinstance(value, list):
        return {}
    metrics: dict[str, FileMetrics] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        path_value = item.get(PATH_FIELD)
        if not isinstance(path_value, str):
            continue
        metric = FileMetrics.from_payload(item)
        metric.ensure_labels()
        metrics[path_value] = metric
    return metrics


__all__ = ["CacheRequest", "CachedEntry", "ResultCache"]
