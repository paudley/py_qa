"""Simple file-based caching for tool outcomes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..models import ToolOutcome
from ..serialization import deserialize_outcome, safe_int, serialize_outcome


@dataclass(frozen=True)
class FileState:
    """Filesystem metadata used to validate cache entries."""

    path: Path
    mtime_ns: int
    size: int


def _collect_file_states(files: Sequence[Path]) -> list[FileState]:
    states: list[FileState] = []
    for path in files:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return []
        states.append(FileState(path.resolve(), stat.st_mtime_ns, stat.st_size))
    return states


class ResultCache:
    """Persist tool outcomes to disk and reload them when inputs are unchanged."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def load(
        self,
        *,
        tool: str,
        action: str,
        cmd: Sequence[str],
        files: Sequence[Path],
        token: str,
    ) -> ToolOutcome | None:
        entry_path = self._entry_path(tool=tool, action=action, cmd=cmd, token=token)
        if not entry_path.is_file():
            return None
        try:
            raw = json.loads(entry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data: dict[str, Any] = raw

        current_states = _collect_file_states(files)
        if files and not current_states:
            return None

        stored_states = _coerce_state_payload(data.get("files"))
        if len(current_states) != len(stored_states):
            return None
        for state in current_states:
            matched = next(
                (item for item in stored_states if item["path"] == str(state.path)),
                None,
            )
            if not matched:
                return None
            if (
                safe_int(matched.get("mtime_ns")) != state.mtime_ns
                or safe_int(matched.get("size")) != state.size
            ):
                return None

        return deserialize_outcome(data)

    def store(
        self,
        *,
        tool: str,
        action: str,
        cmd: Sequence[str],
        files: Sequence[Path],
        token: str,
        outcome: ToolOutcome,
    ) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        entry_path = self._entry_path(tool=tool, action=action, cmd=cmd, token=token)
        states = _collect_file_states(files)
        if files and not states:
            return
        payload = _outcome_to_payload(outcome, states)
        try:
            entry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Cache writes are best-effort; ignore disk errors.
            return

    def _entry_path(
        self,
        *,
        tool: str,
        action: str,
        cmd: Sequence[str],
        token: str,
    ) -> Path:
        hasher = hashlib.sha256()
        hasher.update(tool.encode("utf-8"))
        hasher.update(b"::")
        hasher.update(action.encode("utf-8"))
        hasher.update(b"::")
        hasher.update("\0".join(cmd).encode("utf-8"))
        hasher.update(b"::")
        hasher.update(token.encode("utf-8"))
        digest = hasher.hexdigest()
        return self._dir / f"{digest}.json"


def _outcome_to_payload(
    outcome: ToolOutcome, states: Iterable[FileState]
) -> dict[str, object]:
    payload = serialize_outcome(outcome)
    payload["files"] = [
        {
            "path": str(state.path),
            "mtime_ns": state.mtime_ns,
            "size": state.size,
        }
        for state in states
    ]
    return payload


def _coerce_state_payload(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    states: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict) and "path" in item:
            states.append(item)
    return states


__all__ = ["ResultCache"]
