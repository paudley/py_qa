# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Simple file-based caching for tool outcomes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias, TypedDict, cast

from pydantic import BaseModel, ConfigDict

from ..core.metrics import FileMetrics
from ..core.models import ToolOutcome
from ..core.serialization import deserialize_outcome, safe_int, serialize_outcome
from ..protocols.serialization import JsonValue

JSONValue = JsonValue


COMMAND_DELIMITER: Final[bytes] = b"::"
FILES_FIELD: Final[Literal["files"]] = "files"
FILE_METRICS_FIELD: Final[Literal["file_metrics"]] = "file_metrics"
PATH_FIELD: Final[Literal["path"]] = "path"
MTIME_FIELD: Final[Literal["mtime_ns"]] = "mtime_ns"
SIZE_FIELD: Final[Literal["size"]] = "size"


class StatePayload(TypedDict, total=False):
    """Use this payload to describe serialized file state."""

    path: str
    mtime_ns: int
    size: int


class MetricPayload(TypedDict, total=False):
    """Use this payload to describe serialized file metrics."""

    path: str
    line_count: int
    suppressions: dict[str, int]


CacheJsonValue: TypeAlias = JsonValue | list[StatePayload] | list[MetricPayload]
CachePayload: TypeAlias = dict[str, CacheJsonValue]


@dataclass(frozen=True, slots=True)
class CacheRequest:
    """Use this payload to identify cached command inputs."""

    tool: str
    action: str
    command: tuple[str, ...]
    files: tuple[Path, ...]
    token: str


@dataclass(frozen=True, slots=True)
class CachedEntry:
    """Represent cached tool outcomes along with computed metrics."""

    outcome: ToolOutcome
    file_metrics: dict[str, FileMetrics]


class _CacheMiss(Exception):
    """Raised when a cache entry cannot be used for the current inputs."""


class FileState(BaseModel):
    """Use this model to represent filesystem metadata for cache validation."""

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
    """Use this helper to handle persisted tool outcomes when inputs are unchanged."""

    def __init__(self, directory: Path) -> None:
        """Initialise the cache store rooted at ``directory``.

        Args:
            directory: Filesystem directory used to persist cache entries.
        """

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

        outcome = deserialize_outcome(cast(Mapping[str, JsonValue], payload))
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
        """Persist the outcome for the provided request, ignoring disk errors.

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

        metrics_mapping = dict(file_metrics) if file_metrics is not None else {}

        payload = _outcome_to_payload(outcome, states, metrics_mapping)
        try:
            entry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Cache writes are best-effort; ignore disk errors.
            return

    def _entry_path(self, request: CacheRequest) -> Path:
        """Compute the cache file path associated with ``request``.

        Args:
            request: Cache request describing the tool invocation.

        Returns:
            Path: Filesystem location used to store the cached entry.
        """

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

    def _read_entry(self, entry_path: Path) -> dict[str, JSONValue]:
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
        return cast(dict[str, JSONValue], raw)


def _files_available(files: Sequence[Path], states: tuple[FileState, ...]) -> bool:
    """Return whether all requested files were successfully stat'ed.

    Args:
        files: Files whose presence must be verified.
        states: Collected filesystem metadata for ``files``.

    Returns:
        bool: ``True`` when metadata exists for every file, ``False`` otherwise.
    """

    return not files or bool(states)


def _states_match(
    current_states: tuple[FileState, ...],
    stored_states: tuple[StatePayload, ...],
) -> bool:
    """Return whether ``stored_states`` matches ``current_states``.

    Args:
        current_states: Filesystem metadata gathered for the current run.
        stored_states: Serialized metadata recovered from the cache entry.

    Returns:
        bool: ``True`` when the cached metadata aligns with the current state.
    """

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
) -> CachePayload:
    """Return a serialized payload representing ``outcome``.

    Args:
        outcome: Tool outcome captured from execution.
        states: Filesystem states used to validate cache hits.
        file_metrics: Derived per-file metrics keyed by normalized path.

    Returns:
        CachePayload: JSON-compatible payload persisted to the cache.
    """

    payload: CachePayload = dict(serialize_outcome(outcome))
    state_payloads: list[StatePayload] = [_state_to_payload(state) for state in states]
    payload[FILES_FIELD] = state_payloads
    if file_metrics:
        payload[FILE_METRICS_FIELD] = _metrics_to_payload(file_metrics)
    return payload


def _coerce_state_payload(value: CacheJsonValue | None) -> tuple[StatePayload, ...]:
    """Use this helper to return normalized state payloads extracted from ``value``.

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
        mtime_value = item.get(MTIME_FIELD)
        if isinstance(mtime_value, (int, float, str)):
            payload[MTIME_FIELD] = safe_int(mtime_value)
        size_value = item.get(SIZE_FIELD)
        if isinstance(size_value, (int, float, str)):
            payload[SIZE_FIELD] = safe_int(size_value)
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


def _coerce_metrics_payload(value: CacheJsonValue | None) -> dict[str, FileMetrics]:
    """Use this helper to return ``FileMetrics`` instances from serialized payloads.

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
        metric_payload: dict[str, JsonValue] = {}
        line_count_value = item.get("line_count")
        if isinstance(line_count_value, (int, float, str)):
            metric_payload["line_count"] = line_count_value
        suppressions_value = item.get("suppressions")
        if isinstance(suppressions_value, Mapping):
            clean_suppressions: dict[str, JsonValue] = {}
            for label, count in suppressions_value.items():
                if isinstance(label, str) and isinstance(count, (int, float, str)):
                    clean_suppressions[label] = count
            metric_payload["suppressions"] = clean_suppressions
        metric = FileMetrics.from_payload(metric_payload)
        metric.ensure_labels()
        metrics[path_value] = metric
    return metrics


__all__ = ["CacheRequest", "CachedEntry", "ResultCache"]
