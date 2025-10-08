# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

import pytest

from pyqa.core.runtime import ServiceContainer, ServiceResolutionError, register_default_services


def test_register_and_resolve_singleton() -> None:
    container = ServiceContainer()
    container.register("value", lambda _: object())
    first = container.resolve("value")
    second = container.resolve("value")
    assert first is second


def test_register_non_singleton() -> None:
    container = ServiceContainer()
    container.register("counter", lambda _: object(), singleton=False)
    first = container.resolve("counter")
    second = container.resolve("counter")
    assert first is not second


def test_replace_service() -> None:
    container = ServiceContainer()
    container.register("value", lambda _: "a")
    container.register("value", lambda _: "b", replace=True)
    assert container.resolve("value") == "b"


def test_service_missing() -> None:
    container = ServiceContainer()
    with pytest.raises(ServiceResolutionError):
        container.resolve("missing")


def test_register_default_services() -> None:
    container = ServiceContainer()
    register_default_services(container)
    console_factory = container.resolve("console_factory")
    logger_factory = container.resolve("logger_factory")
    serializer = container.resolve("serializer")
    assert callable(console_factory)
    assert callable(logger_factory)
    dumped = serializer.dump({"value": 1})
    assert serializer.load(dumped)["value"] == 1
    assert callable(container.resolve("catalog_plugins"))
    assert callable(container.resolve("cli_plugins"))
    assert callable(container.resolve("diagnostics_plugins"))
    assert callable(container.resolve("all_plugins"))


def test_service_container_dunder_helpers() -> None:
    container = ServiceContainer()
    container.register("alpha", lambda _: "one")
    container.register("beta", lambda _: "two")

    assert len(container) == 2
    assert "alpha" in container
    assert "missing" not in container
