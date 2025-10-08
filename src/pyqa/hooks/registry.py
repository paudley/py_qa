# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registry helpers describing available git hooks."""

from __future__ import annotations

from collections.abc import Iterable

_DEFAULT_HOOKS: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")


def available_hooks() -> tuple[str, ...]:
    """Return the default sequence of supported git hook names."""

    return _DEFAULT_HOOKS


def is_supported(name: str) -> bool:
    """Return ``True`` when ``name`` identifies a supported hook."""

    return name in _DEFAULT_HOOKS


def normalise_hook_order(hooks: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return hook names ordered consistently with the default registry."""

    if hooks is None:
        return _DEFAULT_HOOKS
    seen: set[str] = set()
    ordered: list[str] = []
    for hook in hooks:
        if hook in seen:
            continue
        if hook in _DEFAULT_HOOKS:
            ordered.append(hook)
            seen.add(hook)
    for hook in _DEFAULT_HOOKS:
        if hook not in seen:
            ordered.append(hook)
    return tuple(ordered)


__all__ = ["available_hooks", "is_supported", "normalise_hook_order"]
