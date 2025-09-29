"""Sample strategy implementations used during loader tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def command_builder(config: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Return a static command tuple derived from the provided configuration.

    Args:
        config: Mapping containing an ``args`` sequence that lists command tokens.

    Returns:
        tuple[str, ...]: Tuple of command arguments defaulting to an empty tuple.
    """

    args = tuple(config.get("args", ()))
    return tuple(str(token) for token in args)


def parser_factory(config: Mapping[str, str]) -> str:
    """Return the configured parser identifier as a sentinel.

    Args:
        config: Mapping that may include an ``id`` key identifying the parser.

    Returns:
        str: Parser identifier when provided, otherwise ``"default-parser"``.
    """

    return config.get("id", "default-parser")
