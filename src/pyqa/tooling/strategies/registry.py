"""Lightweight registry for strategy factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable

StrategyFactory = Callable[..., object]


@dataclass(frozen=True)
class StrategyEntry:
    """Registered strategy metadata."""

    identifier: str
    kind: str
    factory: StrategyFactory


_STRATEGY_REGISTRY: Dict[str, StrategyEntry] = {}


def register_strategy(identifier: str, *, kind: str, factory: StrategyFactory) -> None:
    """Register *factory* under *identifier* for the provided *kind*."""

    existing = _STRATEGY_REGISTRY.get(identifier)
    if existing is not None and existing.factory is not factory:
        raise ValueError(f"strategy '{identifier}' is already registered")
    _STRATEGY_REGISTRY[identifier] = StrategyEntry(identifier=identifier, kind=kind, factory=factory)


def get_strategy(identifier: str) -> StrategyEntry | None:
    """Return the registered entry for *identifier* if present."""

    return _STRATEGY_REGISTRY.get(identifier)


def iter_strategies() -> Iterable[StrategyEntry]:
    """Yield registered strategy entries."""

    return tuple(_STRATEGY_REGISTRY.values())


__all__ = ["StrategyEntry", "StrategyFactory", "get_strategy", "iter_strategies", "register_strategy"]
