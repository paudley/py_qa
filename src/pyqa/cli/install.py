"""Implementation of the `py-qa lint install` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import typer

from ..tool_env import PROJECT_MARKER
from .options import InstallOptions
from .utils import installed_packages, run_uv

DEV_DEPENDENCIES: Tuple[str, ...] = (
    "autopep8",
    "bandit[baseline,toml,sarif]",
    "black",
    "bs4",
    "isort",
    "markdown",
    "mypy-extensions",
    "mypy",
    "pycodestyle",
    "pyflakes",
    "pylint-htmf",
    "pylint-plugin-utils",
    "pylint-pydantic",
    "pylint",
    "pyright",
    "pyupgrade",
    "ruff",
    "twine",
    "types-aiofiles",
    "types-markdown",
    "types-regex",
    "types-decorator",
    "types-pexpect",
    "typing-extensions",
    "typing-inspection",
    "uv",
    "vulture",
)

OPTIONAL_TYPED: Dict[str, Tuple[str, ...]] = {
    "pymysql": ("types-PyMySQL",),
    "cachetools": ("types-cachetools",),
    "cffi": ("types-cffi",),
    "colorama": ("types-colorama",),
    "python-dateutil": ("types-python-dateutil",),
    "defusedxml": ("types-defusedxml",),
    "docutils": ("types-docutils",),
    "gevent": ("types-gevent",),
    "greenlet": ("types-greenlet",),
    "html5lib": ("types-html5lib",),
    "httplib2": ("types-httplib2",),
    "jsonschema": ("types-jsonschema",),
    "libsass": ("types-libsass",),
    "networkx": ("types-networkx",),
    "openpyxl": ("types-openpyxl",),
    "pandas": ("pandas-stubs",),
    "protobuf": ("types-protobuf",),
    "psutil": ("types-psutil",),
    "psycopg2": ("types-psycopg2",),
    "pyasn1": ("types-pyasn1",),
    "pyarrow": ("pyarrow-stubs",),
    "pycurl": ("types-pycurl",),
    "pygments": ("types-pygments",),
    "pyopenssl": ("types-pyopenssl",),
    "pytz": ("types-pytz",),
    "pywin32": ("types-pywin32",),
    "pyyaml": ("types-pyyaml",),
    "requests": ("types-requests",),
    "scipy": ("scipy-stubs",),
    "setuptools": ("types-setuptools",),
    "shapely": ("types-shapely",),
    "simplejson": ("types-simplejson",),
    "tabulate": ("types-tabulate",),
    "tensorflow": ("types-tensorflow",),
    "tqdm": ("types-tqdm",),
}

STUB_GENERATION: Dict[str, Tuple[str, ...]] = {
    "chromadb": ("chromadb",),
    "geopandas": ("geopandas",),
    "polars": ("polars",),
    "pyarrow": ("pyarrow", "pyarrow.parquet"),
    "pyreadstat": ("pyreadstat",),
    "scikit-learn": ("sklearn",),
    "tolerantjson": ("tolerantjson",),
}

PYQA_ROOT = Path(__file__).resolve().parent.parent
STUBS_DIR = PYQA_ROOT / "stubs"
TOOL_CACHE = PYQA_ROOT / ".lint-cache"


def install_command() -> None:
    """Install development dependencies and stubs for pyqa."""

    options = InstallOptions()

    typer.echo("Installing py-qa development dependencies…")
    run_uv(["uv", "add", "-q", "--dev", *DEV_DEPENDENCIES])

    if options.include_optional:
        _install_optional_stubs()

    if options.generate_stubs:
        _generate_runtime_stubs()

    marker = TOOL_CACHE / PROJECT_MARKER.name
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"project": True}), encoding="utf-8")

    typer.echo("Dependency installation complete.")


def _install_optional_stubs() -> None:
    """Install optional stub packages when their runtime is present."""

    installed = installed_packages()
    for pkg, extras in OPTIONAL_TYPED.items():
        if pkg.lower() not in installed:
            continue
        for dep in extras:
            typer.echo(f"Adding optional typing stub {dep}")
            run_uv(["uv", "add", "-q", "--dev", dep], check=False)


def _generate_runtime_stubs() -> None:
    """Generate stub skeletons for runtime packages lacking type hints."""

    installed = installed_packages()
    STUBS_DIR.mkdir(exist_ok=True)
    for pkg, modules in STUB_GENERATION.items():
        if pkg.lower() not in installed:
            continue
        for module in modules:
            target = STUBS_DIR / module
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Generating stubs for {module}")
            run_uv(
                [
                    "uv",
                    "run",
                    "stubgen",
                    "--package",
                    module,
                    "--output",
                    str(target),
                ],
                check=False,
            )
