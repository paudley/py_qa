# SPDX-License-Identifier: MIT
"""BDD entrypoint for wrapper CLI scenarios."""

from pytest_bdd import scenario

@scenario("wrapper/features/cli_wrappers.feature", "Local interpreter is used when probe succeeds")
def test_wrapper_local_interpreter() -> None:
    """Execute scenario via pytest-bdd."""


@scenario("wrapper/features/cli_wrappers.feature", "Fallback to uv when explicit interpreter is too old")
def test_wrapper_uv_fallback() -> None:
    """Execute scenario via pytest-bdd."""


@scenario("wrapper/features/cli_wrappers.feature", "Failing when uv override is missing")
def test_wrapper_missing_uv() -> None:
    """Execute scenario via pytest-bdd."""
