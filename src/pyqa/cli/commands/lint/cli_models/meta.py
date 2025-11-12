# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Meta action dependency factories for the lint CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from ....core.shared import Depends
from ..params import (
    LintMetaParams,
    MetaActionParams,
    MetaAnalysisChecks,
    MetaRuntimeChecks,
    RuntimeAdditionalChecks,
    RuntimeCoreChecks,
    RuntimeGroupOverrides,
    RuntimeInterfaceChecks,
    RuntimePolicyChecks,
)
from .constants import (
    CACHE_HELP,
    CHECK_DI_HELP,
    CHECK_INTERFACES_HELP,
    CHECK_MODULE_DOCS_HELP,
    CLOSURES_HELP,
    CONDITIONAL_IMPORTS_HELP,
    COPYRIGHT_HELP,
    DOCSTRINGS_HELP,
    EXPLAIN_TOOLS_HELP,
    EXPLAIN_TOOLS_JSON_HELP,
    FETCH_ALL_TOOLS_HELP,
    FILE_SIZE_HELP,
    LICENSE_HEADER_HELP,
    MISSING_HELP,
    NORMAL_PRESET_HELP,
    PYQA_PYTHON_HYGIENE_HELP,
    PYQA_RULES_HELP,
    PYTHON_HYGIENE_HELP,
    SCHEMA_SYNC_HELP,
    SHOW_VALID_SUPPRESSIONS_HELP,
    SIGNATURES_HELP,
    SUPPRESSIONS_HELP,
    TOOL_INFO_HELP,
    TYPING_HELP,
    VALIDATE_SCHEMA_HELP,
    VALUE_TYPES_GENERAL_HELP,
)


def _meta_action_toggle_dependency(
    doctor: Annotated[bool, typer.Option(False, "--doctor", help="Run environment diagnostics and exit.")],
    fetch_all_tools: Annotated[bool, typer.Option(False, "--fetch-all-tools", help=FETCH_ALL_TOOLS_HELP)],
    validate_schema: Annotated[bool, typer.Option(False, "--validate-schema", help=VALIDATE_SCHEMA_HELP)],
    normal: Annotated[bool, typer.Option(False, "-n", "--normal", help=NORMAL_PRESET_HELP)],
    explain_tools: Annotated[bool, typer.Option(False, "--explain-tools", help=EXPLAIN_TOOLS_HELP)],
) -> MetaActionParams:
    """Return boolean toggles for meta actions.

    Args:
        doctor: Flag enabling environment diagnostics.
        fetch_all_tools: Flag triggering the fetch-only workflow.
        validate_schema: Flag enabling schema validation.
        normal: Flag selecting the standard lint preset.
        explain_tools: Flag enabling tool explanation output.


    Returns:
        MetaActionParams: Structured toggle state for meta actions.
    """

    return MetaActionParams(
        doctor=doctor,
        tool_info=None,
        fetch_all_tools=fetch_all_tools,
        validate_schema=validate_schema,
        normal=normal,
        explain_tools=explain_tools,
        explain_tools_json=None,
    )


def _meta_action_info_dependency(
    tool_info: Annotated[str | None, typer.Option(None, "--tool-info", metavar="TOOL", help=TOOL_INFO_HELP)],
) -> str | None:
    """Return optional informational CLI toggles.

    Args:
        tool_info: Optional tool name used when requesting tool metadata.

    Returns:
        str | None: Tool name when provided.
    """

    return tool_info


def _meta_action_explain_json_dependency(
    explain_tools_json: str | None = typer.Option(
        None,
        "--explain-tools-json",
        metavar="PATH",
        help=EXPLAIN_TOOLS_JSON_HELP,
    ),
) -> str | None:
    """Return optional path for explain-tools JSON output.

    Args:
        explain_tools_json: Optional filesystem path supplied via the CLI flag.

    Returns:
        str | None: Provided explain-tools JSON path when the flag is used.
    """

    return explain_tools_json


def _meta_action_dependency(
    toggles: Annotated[MetaActionParams, Depends(_meta_action_toggle_dependency)],
    tool_info: Annotated[str | None, Depends(_meta_action_info_dependency)],
    explain_tools_json: Annotated[str | None, Depends(_meta_action_explain_json_dependency)],
) -> MetaActionParams:
    """Return meta-action toggles captured from CLI options.

    Args:
        toggles: Structured meta-action toggle flags.
        tool_info: Optional tool information requested by the user.

    Returns:
        MetaActionParams: Collated meta-action configuration.
    """

    return MetaActionParams(
        doctor=toggles.doctor,
        tool_info=tool_info,
        fetch_all_tools=toggles.fetch_all_tools,
        validate_schema=toggles.validate_schema,
        normal=toggles.normal,
        explain_tools=toggles.explain_tools,
        explain_tools_json=explain_tools_json,
    )


def _meta_analysis_checks_dependency(
    check_docstrings: Annotated[bool, typer.Option(False, "--check-docstrings", help=DOCSTRINGS_HELP)],
    check_suppressions: Annotated[bool, typer.Option(False, "--check-suppressions", help=SUPPRESSIONS_HELP)],
    check_types_strict: Annotated[bool, typer.Option(False, "--check-types-strict", help=TYPING_HELP)],
    check_missing: Annotated[bool, typer.Option(False, "--check-missing", help=MISSING_HELP)],
) -> MetaAnalysisChecks:
    """Return analysis-focused meta-check toggles.

    Args:
        check_docstrings: Flag enabling docstring compliance checks.
        check_suppressions: Flag validating suppression justifications.
        check_types_strict: Flag enforcing strict typing requirements.
        check_missing: Flag checking for missing dependency declarations.

    Returns:
        MetaAnalysisChecks: Structured meta-analysis check toggles.
    """

    return MetaAnalysisChecks(
        check_docstrings=check_docstrings,
        check_suppressions=check_suppressions,
        check_types_strict=check_types_strict,
        check_missing=check_missing,
    )


def _runtime_value_type_checks_dependency(
    check_value_types: Annotated[
        bool,
        typer.Option(
            False,
            "--check-value-types",
            help="Verify pyqa value-type helpers expose ergonomic dunder methods.",
        ),
    ],
    check_value_types_general: Annotated[
        bool,
        typer.Option(False, "--check-value-types-general", help=VALUE_TYPES_GENERAL_HELP),
    ],
) -> dict[str, bool]:
    """Return value-type-specific runtime toggles.

    Args:
        check_value_types: Flag checking value-type ergonomics.
        check_value_types_general: Flag checking general value-type usage.

    Returns:
        dict[str, bool]: Structured value-type runtime toggles.
    """

    return {
        "check_value_types": check_value_types,
        "check_value_types_general": check_value_types_general,
    }


def _runtime_core_checks_dependency(
    check_closures: Annotated[bool, typer.Option(False, "--check-closures", help=CLOSURES_HELP)],
    check_conditional_imports: Annotated[
        bool,
        typer.Option(
            False,
            "--check-conditional-imports",
            help=CONDITIONAL_IMPORTS_HELP,
        ),
    ],
    check_signatures: Annotated[bool, typer.Option(False, "--check-signatures", help=SIGNATURES_HELP)],
    check_cache_usage: Annotated[bool, typer.Option(False, "--check-cache-usage", help=CACHE_HELP)],
    value_types: Annotated[dict[str, bool], Depends(_runtime_value_type_checks_dependency)],
) -> dict[str, bool]:
    """Return the runtime core check toggles.

    Args:
        check_closures: Flag validating closure usage.
        check_conditional_imports: Flag detecting conditional import usage.
        check_signatures: Flag validating function signatures.
        check_cache_usage: Flag ensuring cache helpers are used correctly.
        value_types: Structured value-type runtime toggles.

    Returns:
        dict[str, bool]: Structured runtime core check toggles.
    """

    return {
        "check_closures": check_closures,
        "check_conditional_imports": check_conditional_imports,
        "check_signatures": check_signatures,
        "check_cache_usage": check_cache_usage,
        **value_types,
    }


def _runtime_interface_checks_dependency(
    check_interfaces: Annotated[bool, typer.Option(False, "--check-interfaces", help=CHECK_INTERFACES_HELP)],
    check_di: Annotated[bool, typer.Option(False, "--check-di", help=CHECK_DI_HELP)],
    check_module_docs: Annotated[bool, typer.Option(False, "--check-module-docs", help=CHECK_MODULE_DOCS_HELP)],
    check_pyqa_python_hygiene: Annotated[
        bool,
        typer.Option(False, "--check-pyqa-python-hygiene", help=PYQA_PYTHON_HYGIENE_HELP),
    ],
) -> dict[str, bool]:
    """Return interface-oriented runtime toggles.

    Args:
        check_interfaces: Flag ensuring interface contracts are satisfied.
        check_di: Flag validating dependency injection boundaries.
        check_module_docs: Flag checking module documentation presence.
        check_pyqa_python_hygiene: Flag enforcing pyqa-specific hygiene rules.

    Returns:
        dict[str, bool]: Structured runtime interface toggles.
    """

    return {
        "check_interfaces": check_interfaces,
        "check_di": check_di,
        "check_module_docs": check_module_docs,
        "check_pyqa_python_hygiene": check_pyqa_python_hygiene,
    }


def _runtime_policy_checks_dependency(
    show_valid_suppressions: Annotated[
        bool, typer.Option(False, "--show-valid-suppressions", help=SHOW_VALID_SUPPRESSIONS_HELP)
    ],
    check_license_header: Annotated[bool, typer.Option(False, "--check-license-header", help=LICENSE_HEADER_HELP)],
    check_copyright: Annotated[bool, typer.Option(False, "--check-copyright", help=COPYRIGHT_HELP)],
    check_python_hygiene: Annotated[bool, typer.Option(False, "--check-python-hygiene", help=PYTHON_HYGIENE_HELP)],
) -> dict[str, bool]:
    """Return policy-oriented runtime toggles.

    Args:
        show_valid_suppressions: Flag printing valid suppression markers.
        check_license_header: Flag verifying license headers.
        check_copyright: Flag verifying copyright statements.
        check_python_hygiene: Flag enforcing generic Python hygiene.

    Returns:
        dict[str, bool]: Structured runtime policy toggles.
    """

    return {
        "show_valid_suppressions": show_valid_suppressions,
        "check_license_header": check_license_header,
        "check_copyright": check_copyright,
        "check_python_hygiene": check_python_hygiene,
    }


def _runtime_additional_checks_dependency(
    check_file_size: Annotated[bool, typer.Option(False, "--check-file-size", help=FILE_SIZE_HELP)],
    check_schema_sync: Annotated[bool, typer.Option(False, "--check-schema-sync", help=SCHEMA_SYNC_HELP)],
    pyqa_rules: Annotated[bool, typer.Option(False, "--pyqa-rules", help=PYQA_RULES_HELP)],
) -> dict[str, bool]:
    """Return advanced runtime toggle selections.

    Args:
        check_file_size: Flag enforcing file size limits.
        check_schema_sync: Flag validating schema synchronisation.
        pyqa_rules: Flag enabling pyqa-specific rule validations.

    Returns:
        dict[str, bool]: Structured additional runtime toggles.
    """

    return {
        "check_file_size": check_file_size,
        "check_schema_sync": check_schema_sync,
        "pyqa_rules": pyqa_rules,
    }


def _meta_runtime_checks_dependency(
    core: Annotated[dict[str, bool], Depends(_runtime_core_checks_dependency)],
    interface: Annotated[dict[str, bool], Depends(_runtime_interface_checks_dependency)],
    policy: Annotated[dict[str, bool], Depends(_runtime_policy_checks_dependency)],
    additional: Annotated[dict[str, bool], Depends(_runtime_additional_checks_dependency)],
) -> MetaRuntimeChecks:
    """Return runtime-focused meta-check toggles.

    Args:
        core: Structured core runtime check toggles.
        interface: Structured interface runtime check toggles.
        policy: Structured policy runtime check toggles.
        additional: Structured additional runtime check toggles.

    Returns:
        MetaRuntimeChecks: Consolidated runtime check configuration.
    """

    overrides = RuntimeGroupOverrides(
        core=RuntimeCoreChecks(**core),
        interface=RuntimeInterfaceChecks(**interface),
        policy=RuntimePolicyChecks(**policy),
        additional=RuntimeAdditionalChecks(**additional),
    )
    return MetaRuntimeChecks(overrides=overrides)


def _meta_params_dependency(
    actions: Annotated[MetaActionParams, Depends(_meta_action_dependency)],
    analysis_checks: Annotated[MetaAnalysisChecks, Depends(_meta_analysis_checks_dependency)],
    runtime_checks: Annotated[MetaRuntimeChecks, Depends(_meta_runtime_checks_dependency)],
) -> LintMetaParams:
    """Return meta-command parameters influencing lint execution flow.

    Args:
        actions: Meta-action toggles derived from CLI inputs.
        analysis_checks: Meta-analysis check toggles derived from CLI inputs.
        runtime_checks: Meta-runtime check toggles derived from CLI inputs.

    Returns:
        LintMetaParams: Structured meta command parameters applied to execution.
    """

    if actions.normal:
        analysis = MetaAnalysisChecks(
            check_docstrings=True,
            check_suppressions=True,
            check_types_strict=True,
            check_missing=True,
        )
        runtime_overrides = RuntimeGroupOverrides(
            core=RuntimeCoreChecks(
                check_closures=True,
                check_conditional_imports=True,
                check_signatures=True,
                check_cache_usage=True,
                check_value_types=True,
                check_value_types_general=True,
            ),
            interface=RuntimeInterfaceChecks(
                check_interfaces=True,
                check_di=True,
                check_module_docs=True,
                check_pyqa_python_hygiene=True,
            ),
            policy=RuntimePolicyChecks(
                show_valid_suppressions=False,
                check_license_header=True,
                check_copyright=True,
                check_python_hygiene=True,
            ),
            additional=RuntimeAdditionalChecks(
                check_file_size=True,
                check_schema_sync=True,
                pyqa_rules=True,
            ),
        )
        runtime = MetaRuntimeChecks(overrides=runtime_overrides)
    else:
        analysis = analysis_checks
        runtime = runtime_checks

    return LintMetaParams(actions=actions, analysis=analysis, runtime=runtime)


__all__ = [
    "MetaActionParams",
    "MetaAnalysisChecks",
    "MetaRuntimeChecks",
    "_meta_action_dependency",
    "_meta_action_info_dependency",
    "_meta_action_toggle_dependency",
    "_meta_analysis_checks_dependency",
    "_meta_params_dependency",
    "_meta_runtime_checks_dependency",
    "_runtime_additional_checks_dependency",
    "_runtime_core_checks_dependency",
    "_runtime_interface_checks_dependency",
    "_runtime_policy_checks_dependency",
]
