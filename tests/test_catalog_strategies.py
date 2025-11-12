# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Unit tests covering catalog strategy helpers."""

from __future__ import annotations

import pytest

from pyqa.catalog.loader import CatalogIntegrityError
from pyqa.catalog.strategies import command_download_binary, install_download_artifact


def test_install_download_artifact_rejects_non_string_version() -> None:
    """Installer configuration must provide string versions when specified."""

    config = {
        "download": {
            "uri": "https://example.com/tool",
        },
        "version": 123,
    }

    with pytest.raises(CatalogIntegrityError, match="version"):
        install_download_artifact(config)


def test_command_download_binary_rejects_non_boolean_default_to_root() -> None:
    """Target selectors must declare boolean ``defaultToRoot`` flags."""

    config = {
        "download": {
            "uri": "https://example.com/tool",
        },
        "targets": {
            "defaultToRoot": "yes",
        },
    }

    with pytest.raises(CatalogIntegrityError, match="defaultToRoot"):
        command_download_binary(config)
