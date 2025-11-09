# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Metadata toggle interfaces shared with lint execution helpers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetaActionParamsView(Protocol):
    """Protocol describing meta action toggles supplied by the CLI."""

    __slots__ = ()

    @property
    @abstractmethod
    def tool_info(self) -> str | None:
        """Return the optional tool name requested for metadata output.

        Returns:
            str | None: Tool name requested for metadata output.
        """

    @property
    @abstractmethod
    def doctor(self) -> bool:
        """Return ``True`` when diagnostics should run and exit immediately.

        Returns:
            bool: ``True`` when diagnostics should run and exit immediately.
        """

    @property
    @abstractmethod
    def normal(self) -> bool:
        """Return ``True`` when the normal preset should be applied.

        Returns:
            bool: ``True`` when the normal preset is active.
        """

    @property
    @abstractmethod
    def fetch_all_tools(self) -> bool:
        """Return ``True`` when tool downloads should be triggered.

        Returns:
            bool: ``True`` when tool downloads should be triggered.
        """

    @property
    @abstractmethod
    def validate_schema(self) -> bool:
        """Return ``True`` when schema validation is requested.

        Returns:
            bool: ``True`` when schema validation is requested.
        """

    @property
    @abstractmethod
    def explain_tools(self) -> bool:
        """Return ``True`` when tool explanations should be rendered.

        Returns:
            bool: ``True`` when tool explanations should be rendered.
        """


@runtime_checkable
class MetaAnalysisChecksView(Protocol):
    """Protocol describing analysis-oriented meta toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def check_types_strict(self) -> bool:
        """Return ``True`` when strict type checking is enabled.

        Returns:
            bool: ``True`` when strict type checking is enabled.
        """

    @property
    @abstractmethod
    def check_docstrings(self) -> bool:
        """Return ``True`` when docstring validation is enabled.

        Returns:
            bool: ``True`` when docstring validation is enabled.
        """

    @property
    @abstractmethod
    def check_missing(self) -> bool:
        """Return ``True`` when missing dependency checks are enabled.

        Returns:
            bool: ``True`` when missing dependency checks are enabled.
        """

    @property
    @abstractmethod
    def check_suppressions(self) -> bool:
        """Return ``True`` when suppression validation is enabled.

        Returns:
            bool: ``True`` when suppression validation is enabled.
        """


@runtime_checkable
class RuntimeCoreChecksView(Protocol):
    """Protocol describing runtime core lint toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def check_closures(self) -> bool:
        """Return ``True`` when closure validation is enabled.

        Returns:
            bool: ``True`` when closure validation is enabled.
        """

    @property
    @abstractmethod
    def check_conditional_imports(self) -> bool:
        """Return ``True`` when conditional import checks are enabled.

        Returns:
            bool: ``True`` when conditional import checks are enabled.
        """

    @property
    @abstractmethod
    def check_signatures(self) -> bool:
        """Return ``True`` when signature validation is enabled.

        Returns:
            bool: ``True`` when signature validation is enabled.
        """

    @property
    @abstractmethod
    def check_cache_usage(self) -> bool:
        """Return ``True`` when cache usage validation is enabled.

        Returns:
            bool: ``True`` when cache usage validation is enabled.
        """

    @property
    @abstractmethod
    def check_value_types(self) -> bool:
        """Return ``True`` when value-type validation is enabled.

        Returns:
            bool: ``True`` when value-type validation is enabled.
        """

    @property
    @abstractmethod
    def check_value_types_general(self) -> bool:
        """Return ``True`` when general value-type validation is enabled.

        Returns:
            bool: ``True`` when general value-type validation is enabled.
        """


@runtime_checkable
class RuntimeInterfaceChecksView(Protocol):
    """Protocol describing runtime interface lint toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def check_interfaces(self) -> bool:
        """Return ``True`` when interface checks are enabled.

        Returns:
            bool: ``True`` when interface checks are enabled.
        """

    @property
    @abstractmethod
    def check_di(self) -> bool:
        """Return ``True`` when dependency-injection checks are enabled.

        Returns:
            bool: ``True`` when dependency-injection checks are enabled.
        """

    @property
    @abstractmethod
    def check_module_docs(self) -> bool:
        """Return ``True`` when module documentation checks are enabled.

        Returns:
            bool: ``True`` when module documentation checks are enabled.
        """

    @property
    @abstractmethod
    def check_pyqa_python_hygiene(self) -> bool:
        """Return ``True`` when pyqa-specific hygiene checks are enabled.

        Returns:
            bool: ``True`` when pyqa-specific hygiene checks are enabled.
        """


@runtime_checkable
class RuntimePolicyChecksView(Protocol):
    """Protocol describing runtime policy lint toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def show_valid_suppressions(self) -> bool:
        """Return ``True`` when valid suppression reporting is enabled.

        Returns:
            bool: ``True`` when valid suppression reporting is enabled.
        """

    @property
    @abstractmethod
    def check_license_header(self) -> bool:
        """Return ``True`` when license header validation is enabled.

        Returns:
            bool: ``True`` when license header validation is enabled.
        """

    @property
    @abstractmethod
    def check_copyright(self) -> bool:
        """Return ``True`` when copyright validation is enabled.

        Returns:
            bool: ``True`` when copyright validation is enabled.
        """

    @property
    @abstractmethod
    def check_python_hygiene(self) -> bool:
        """Return ``True`` when Python hygiene validation is enabled.

        Returns:
            bool: ``True`` when Python hygiene validation is enabled.
        """


@runtime_checkable
class RuntimeAdditionalChecksView(Protocol):
    """Protocol describing additional runtime lint toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def check_file_size(self) -> bool:
        """Return ``True`` when file size checks are enabled.

        Returns:
            bool: ``True`` when file size checks are enabled.
        """

    @property
    @abstractmethod
    def check_schema_sync(self) -> bool:
        """Return ``True`` when schema sync checks are enabled.

        Returns:
            bool: ``True`` when schema sync checks are enabled.
        """

    @property
    @abstractmethod
    def pyqa_rules(self) -> bool:
        """Return ``True`` when pyqa rules checks are enabled.

        Returns:
            bool: ``True`` when pyqa rules checks are enabled.
        """


@runtime_checkable
class MetaRuntimeChecksView(Protocol):
    """Protocol describing grouped runtime lint toggles."""

    __slots__ = ()

    @property
    @abstractmethod
    def core(self) -> RuntimeCoreChecksView:
        """Return the core runtime lint toggles.

        Returns:
            RuntimeCoreChecksView: Core runtime lint toggles.
        """

    @property
    @abstractmethod
    def interface(self) -> RuntimeInterfaceChecksView:
        """Return the interface runtime lint toggles.

        Returns:
            RuntimeInterfaceChecksView: Interface runtime lint toggles.
        """

    @property
    @abstractmethod
    def policy(self) -> RuntimePolicyChecksView:
        """Return the policy runtime lint toggles.

        Returns:
            RuntimePolicyChecksView: Policy runtime lint toggles.
        """

    @property
    @abstractmethod
    def additional(self) -> RuntimeAdditionalChecksView:
        """Return the additional runtime lint toggles.

        Returns:
            RuntimeAdditionalChecksView: Additional runtime lint toggles.
        """


@runtime_checkable
class LintMetaParams(Protocol):
    """Protocol describing lint meta parameter bundles."""

    __slots__ = ()

    @property
    @abstractmethod
    def actions(self) -> MetaActionParamsView:
        """Return meta action toggles.

        Returns:
            MetaActionParamsView: Meta action toggle bundle.
        """

    @property
    @abstractmethod
    def analysis(self) -> MetaAnalysisChecksView:
        """Return meta analysis toggles.

        Returns:
            MetaAnalysisChecksView: Meta analysis toggle bundle.
        """

    @property
    @abstractmethod
    def runtime(self) -> MetaRuntimeChecksView:
        """Return grouped runtime toggles.

        Returns:
            MetaRuntimeChecksView: Grouped runtime toggle bundle.
        """

    @abstractmethod
    def __getattr__(self, attribute: str) -> bool | str | None:
        """Return the value of an attribute proxied through meta parameters.

        Args:
            attribute: Attribute name expected to resolve through meta toggles.

        Returns:
            bool | str | None: Resolved attribute value.
        """


__all__ = [
    "LintMetaParams",
    "MetaActionParamsView",
    "MetaAnalysisChecksView",
    "MetaRuntimeChecksView",
    "RuntimeAdditionalChecksView",
    "RuntimeCoreChecksView",
    "RuntimeInterfaceChecksView",
    "RuntimePolicyChecksView",
]
