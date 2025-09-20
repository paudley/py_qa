#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# pylint: disable=bad-builtin
"""Spectra Lint Orchestrator (stdlib-only).

This script is the heart of the Spectra lint pipeline. It coordinates discovery,
installation, and execution of a polyglot tool suite across a monorepo without
relying on third-party Python dependencies. If you are extending or debugging
`lint.py`, keep these design pillars in mind:

* **stdlib only** – Every feature must use Python's standard library so the
  script can ship as a standalone executable. Adding external imports breaks
  our packaging assumptions.
* **Workspace aware** – The code enumerates logical "workspaces" (Python
  package, React app, Go service, etc.) and runs only the tools that make sense
  for that subtree. When introducing new language support, hook into the
  workspace detection first so installs, caching, and output grouping remain
  consistent.
* **Agent friendly** – Output defaults to a concise, deterministic format so
  humans and automation can iterate quickly. Preserve the `output` modes and
  ensure new logging stays terse.
* **Safe by default** – Directories such as `node_modules`, `.venv`, `build/`
  are globally excluded. Tools inherit these exclusions where supported. Any
  new integration should extend the same safety posture.
* **Respect local workflows** – `--gitignore` mirrors developers' Git ignore
  rules, `--pre-commit` surfaces staged-only changes, and installers prefer the
  project's virtual environment. When modifying discovery or execution, double
  check that these knobs still behave.

The script is large; the section headers that follow group related behaviour.
If you are adding a sizeable subsystem, introduce a new header and document the
intent so future maintainers (or automation) can navigate quickly.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from functools import lru_cache
import hashlib
import importlib.util
import json

# ---------------- Globals ----------------
# --- venv-first PATH handling (injected) ---
import os
import os as _os
from pathlib import Path
import pathlib as _pathlib
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Final, Literal, Protocol, TypeAlias


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"
    NOTE = "note"


def _venv_bin(_root: _pathlib.Path = _pathlib.Path(".")) -> _pathlib.Path | None:
    # Try .venv/bin (posix) and .venv\Scripts (windows)
    v = _root / ".venv"
    posix = v / "bin"
    win = v / "Scripts"
    if posix.exists():
        return posix
    if win.exists():
        return win
    return None


# If a project .venv exists, ensure its bin/Scripts is first on PATH to prefer local tools
try:
    _vb = _venv_bin(_pathlib.Path(__file__).resolve().parent)
except Exception:
    _vb = _venv_bin(_pathlib.Path("."))
if _vb and _vb.exists():
    _os.environ["PATH"] = str(_vb) + _os.pathsep + _os.environ.get("PATH", "")
# --- end injection ---


def _install_with_preferred_pip(
    args_list: list[str],
) -> subprocess.CompletedProcess[str]:
    vb = _venv_bin(_pathlib.Path(__file__).resolve().parent if "__file__" in globals() else _pathlib.Path("."))
    try:
        from shutil import which as _which
    except Exception:
        import shutil as _shutil

        _which = _shutil.which

    # Get the working directory (where lint.py was invoked)
    cwd = _pathlib.Path.cwd()

    # Prefer uv add --dev if pyproject.toml exists and uv is available
    if (cwd / "pyproject.toml").is_file() and _which("uv"):
        cp = run(["uv", "add", "-q", "--dev"] + args_list)
        if cp.returncode == 0:
            return cp
        # If uv add fails, fall back to pip install methods
        warn(
            "uv add --dev failed; falling back to pip install methods",
            use_emoji=False,
        )

    # Prefer project .venv pip
    if vb and (vb / "pip").exists():
        return run([str(vb / "pip"), "install", "-U"] + args_list)
    # Then uv pip
    if _which("uv"):
        cp = run(["uv", "pip", "install", "-U"] + args_list)
        if cp.returncode != 0:
            warn(
                "uv pip install failed; trying 'uv run -m pip'",
                use_emoji=False,
            )
            return run(["uv", "run", "-m", "pip", "install", "-U"] + args_list)
        return cp
    # Finally system pip
    if pip_exe := _which("pip3") or _which("pip"):
        return run([pip_exe, "install", "-U"] + args_list)
    return subprocess.CompletedProcess([], 1, "", "pip not found")  # type: ignore[return-value]


# --- Decomposed Configuration (SRP) ---


@dataclass
class FileDiscoveryConfig:
    """Configuration for how to discover and filter files."""

    roots: list[Path] = field(default_factory=lambda: [Path(".")])
    excludes: list[Path] = field(default_factory=list)
    paths_from_stdin: bool = False
    # Git-related discovery
    changed_only: bool = False
    diff_ref: str = "HEAD"
    include_untracked: bool = True
    base_branch: str | None = None
    pre_commit: bool = False
    respect_gitignore: bool = False


@dataclass
class OutputConfig:
    """Configuration for controlling output, reporting, and artifacts."""

    verbose: bool = False
    emoji: bool = True
    color: bool = True
    show_passing: bool = False
    output: Literal["pretty", "raw", "concise"] = "concise"
    pretty_format: Literal["text", "jsonl", "markdown"] = "text"
    group_by_code: bool = False
    # Machine-readable reports
    report: Literal["json"] | None = None
    report_out: Path | None = None
    report_include_raw: bool = False
    sarif_out: Path | None = None
    pr_summary_out: Path | None = None
    pr_summary_limit: int = 100
    # CI/GitHub Actions integration
    gha_annotations: bool = False
    annotations_use_json: bool = False


@dataclass
class ExecutionConfig:
    """Configuration for controlling how tools are executed."""

    only: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    enable: list[str] = field(default_factory=list)
    strict: bool = False
    jobs: int = 4
    fix_only: bool = False
    check_only: bool = False
    force_all: bool = False
    respect_config: bool = False
    # Cache settings
    cache_enabled: bool = True
    cache_dir: Path = field(default_factory=lambda: Path(".lint-cache"))


@dataclass
class DedupeConfig:
    """Configuration for deduplicating diagnostics."""

    dedupe: bool = False
    dedupe_by: Literal["first", "severity", "prefer"] = "first"
    dedupe_prefer: list[str] = field(default_factory=list)
    dedupe_line_fuzz: int = 2
    dedupe_same_file_only: bool = True


@dataclass
class Config:
    """Main configuration container, composing smaller configs."""

    file_discovery: FileDiscoveryConfig
    output: OutputConfig
    execution: ExecutionConfig
    dedupe: DedupeConfig
    severity_rules: list[str] = field(default_factory=list)


ROOT = Path.cwd()
TOP_ROOT = ROOT  # original project root (set in main)
GLOBAL_CFG = None

NODE_ENV_DEFAULTS: Final[dict[str, str]] = {
    "CI": "1",
    "npm_config_yes": "true",
    "npm_config_fund": "false",
    "npm_config_audit": "false",
    "npm_config_progress": "false",
    "NPX_SILENT": "1",
}

NODE_EXECUTABLE_HINTS: Final[tuple[str, ...]] = (
    "node",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "bun",
    "prettier",
    "eslint",
    "tsc",
    "jest",
)


_PY_DEF_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PY_CLASS_RE: Final[re.Pattern[str]] = re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|:)?")
_TS_CLASS_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z0-9_$]+)")
_TS_FUNC_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z0-9_$]+)")
_TS_METHOD_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+)*([A-Za-z0-9_$]+)\s*\("
)
_TS_CONST_FUNC_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:function\b|\()"
)

ALWAYS_EXCLUDE_DIRS: Final[set[str]] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "coverage",
}

LANGUAGE_MARKERS: Final[dict[str, set[str]]] = {
    "python": {
        "pyproject.toml",
        "setup.cfg",
        "requirements.txt",
        "pipfile",
        "poetry.lock",
    },
    "javascript": {
        "package.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.json",
    },
    "go": {"go.mod"},
    "rust": {"Cargo.toml"},
}

LANGUAGE_EXTENSIONS: Final[dict[str, set[str]]] = {
    "python": {".py", ".pyi"},
    "javascript": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
    "go": {".go"},
    "rust": {".rs"},
    "markdown": {".md", ".mdx", ".markdown"},
}


def is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "blue": "\033[34;1m",
    "cyan": "\033[36;1m",
    "red": "\033[31;1m",
    "green": "\033[32;1m",
    "yellow": "\033[33;1m",
}


def colorize(txt: str, code: str, enable: bool) -> str:
    return f"{ANSI.get(code,'')}{txt}{ANSI['reset']}" if enable and is_tty() else txt


def emoji(sym: str, enable: bool) -> str:
    return sym if enable else ""


def section(title: str, *, use_color: bool) -> None:
    print(f"\n{colorize('───','blue',use_color)} {colorize(title,'cyan',use_color)} {colorize('───','blue',use_color)}")


def info(msg: str, *, use_emoji: bool) -> None:
    print(f"{emoji('ℹ️ ',use_emoji)}{msg}")


def ok(msg: str, *, use_emoji: bool) -> None:
    print(f"{emoji('✅ ',use_emoji)}{msg}")


def warn(msg: str, *, use_emoji: bool) -> None:
    print(f"{emoji('⚠️ ',use_emoji)}{msg}")


def fail(msg: str, *, use_emoji: bool) -> None:
    print(f"{emoji('❌ ',use_emoji)}{msg}")


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env: dict[str, str] | None = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)

    def _ensure_text(data: str | bytes | None) -> str:
        if isinstance(data, bytes):
            return data.decode(errors="ignore")
        return data or ""

    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=full_env,
            text=True,
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        stdout = _ensure_text(exc.stdout)
        stderr_base = _ensure_text(exc.stderr)
        timeout_msg = f"Command timed out after {timeout:.1f}s" if timeout is not None else "Command timed out"
        stderr = f"{stderr_base}\n{timeout_msg}" if stderr_base else timeout_msg
        return subprocess.CompletedProcess(
            args=exc.cmd if isinstance(exc.cmd, list) else cmd,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )


def _has_any(path: Path, names: Iterable[str]) -> bool:
    return any(any(path.glob(n)) for n in names)


def respect_config_cmd(tool_name: str, base_cmd: list[str], root: Path) -> list[str]:
    tool_def = next((t for t in ALL_TOOLS if t.name == tool_name), None)
    cfg_files: list[str] = []
    if not tool_def:
        # Fallback for tools not in ALL_TOOLS (e.g., go tools)
        if tool_name in {"golangci-lint", "go", "cargo", "clippy", "cargo-fmt"}:
            cfg_files = [".golangci.yml", ".golangci.yaml", "go.mod", "Cargo.toml"]
        else:
            return base_cmd
    elif not tool_def.config_files:
        return base_cmd
    else:
        cfg_files = list(tool_def.config_files)

    if any((root / f).exists() for f in cfg_files if "*" not in f) or _has_any(
        root, {f for f in cfg_files if "*" in f}
    ):
        prog = base_cmd[:1]
        rest = []
        if tool_name == "tsc":
            rest = ["--noEmit"]
        return prog + rest
    return base_cmd


# ---------------- File discovery & git ----------------
def _contains_forbidden_dir(path: Path) -> bool:
    return any(part in ALWAYS_EXCLUDE_DIRS for part in path.parts)


def list_repo_files(
    roots: list[Path],
    *,
    excludes: list[Path],
    prefer_git: bool = True,
    respect_gitignore: bool = False,
) -> list[Path]:
    excludes_set = {p.resolve() for p in excludes}
    repo_root: Path | None = None
    results: set[Path] = set()

    def _is_excluded(path: Path) -> bool:
        if _contains_forbidden_dir(path):
            return True
        if any(part.startswith(".") and part not in {".", ".."} for part in path.parts):
            return True
        try:
            resolved = path.resolve()
        except OSError:
            resolved = (Path.cwd() / path).resolve()
        for exc in excludes_set:
            try:
                resolved.relative_to(exc)
            except ValueError:
                continue
            else:
                return True
        return False

    def _within_roots(path: Path, file_roots: set[Path], dir_roots: set[Path]) -> bool:
        if path in file_roots:
            return True
        for d in dir_roots:
            try:
                path.relative_to(d)
            except ValueError:
                continue
            else:
                return True
        return False

    try:
        file_roots = {r.resolve() for r in roots if r.is_file()}
    except Exception:
        file_roots = set()
    try:
        dir_roots = {r.resolve() for r in roots if r.is_dir()}
    except Exception:
        dir_roots = set()

    if prefer_git and which("git"):
        cp_root = run(["git", "rev-parse", "--show-toplevel"])
        if cp_root.returncode == 0:
            repo_root = Path(cp_root.stdout.strip())
            cmd = ["git", "ls-files", "--cached"]
            if respect_gitignore:
                cmd.extend(["--others", "--exclude-standard"])
            cp = run(cmd, cwd=repo_root)
            if cp.returncode == 0:
                for line in cp.stdout.splitlines():
                    rel = Path(line.strip())
                    abs_path = repo_root / rel
                    if not abs_path.exists():
                        continue
                    if not _within_roots(abs_path.resolve(), file_roots, dir_roots):
                        continue
                    if _is_excluded(abs_path):
                        continue
                    if abs_path.is_file():
                        results.add(abs_path)
                if results or respect_gitignore:
                    return sorted(results)

    for root in roots:
        if root.is_file():
            if not _is_excluded(root):
                results.add(root.resolve())
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in ALWAYS_EXCLUDE_DIRS and not _is_excluded(current_dir / d)]
            for fn in filenames:
                p = current_dir / fn
                if _is_excluded(p):
                    continue
                results.add(p.resolve())
    return sorted(results)


def git_changed_paths(diff_ref: str = "HEAD", include_untracked: bool = True) -> list[Path]:
    paths: set[Path] = set()
    cp1 = run(["git", "diff", "--name-only", diff_ref])
    if cp1.returncode == 0:
        paths.update(Path(x.strip()) for x in cp1.stdout.splitlines() if x.strip())
    cp2 = run(["git", "diff", "--name-only", "--cached", diff_ref])
    if cp2.returncode == 0:
        paths.update(Path(x.strip()) for x in cp2.stdout.splitlines() if x.strip())
    if include_untracked:
        cp3 = run(["git", "ls-files", "--others", "--exclude-standard"])
        if cp3.returncode == 0:
            paths.update(Path(x.strip()) for x in cp3.stdout.splitlines() if x.strip())
    filtered: set[Path] = set()
    for p in paths:
        absolute = p if p.is_absolute() else (Path.cwd() / p)
        try:
            resolved = absolute.resolve()
        except OSError:
            continue
        if not resolved.exists():
            continue
        if _contains_forbidden_dir(resolved):
            continue
        if any(part.startswith(".") and part not in {".", ".."} for part in resolved.parts):
            continue
        filtered.add(resolved)
    return sorted(filtered)


def git_staged_paths() -> list[Path]:
    if not which("git"):
        return []
    cp = run(["git", "diff", "--name-only", "--cached"])
    if cp.returncode != 0:
        return []
    results: list[Path] = []
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        candidate = Path(line.strip())
        absolute = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
        try:
            resolved = absolute.resolve()
        except OSError:
            continue
        if not resolved.exists():
            continue
        if _contains_forbidden_dir(resolved):
            continue
        if any(part.startswith(".") and part not in {".", ".."} for part in resolved.parts):
            continue
        results.append(resolved)
    return results


def git_merge_base(base_branch: str) -> str | None:
    if not which("git"):
        return None
    cp = run(["git", "merge-base", "HEAD", base_branch])
    if cp.returncode == 0:
        sha = cp.stdout.strip()
        return sha if sha else None
    return None


# ---------------- Filters ----------------
@dataclass
class OutputFilter:
    patterns: Iterable[str] = field(default_factory=tuple)
    _compiled_patterns: list[re.Pattern[str]] = field(init=False, repr=False, default_factory=list)

    def __post_init__(self) -> None:
        self._compiled_patterns = [re.compile(p) for p in self.patterns]

    def apply(self, text: str) -> str:
        if not text or not self._compiled_patterns:
            return text
        return "\n".join(line for line in text.splitlines() if not any(p.search(line) for p in self._compiled_patterns))


# ---------------- Data structures ----------------
@dataclass
class Diagnostic:
    file: str | None
    line: int | None
    col: int | None
    severity: Severity
    message: str
    title: str
    code: str | None
    group: str | None = None


FlatDiagnostic: TypeAlias = tuple[str, str, int, int, Diagnostic, int]


@dataclass
class RawDiagnostic:
    """A type-safe intermediate representation of a diagnostic."""

    file: str | None
    line: int | None
    col: int | None
    severity: Severity | str
    message: str
    code: str | None = None
    source: str | None = None  # Tool name, useful for context


@dataclass
class DeferredCommand:
    """A wrapper to defer command finalization until config is available."""

    base_cmd: list[str]
    tool_name: str

    def realize(self, cfg: Config, root: Path) -> list[str]:
        if not getattr(cfg.execution, "respect_config", False):
            return self.base_cmd
        return respect_config_cmd(self.tool_name, self.base_cmd, root)


@dataclass
class ToolAction:
    name: str
    cmd: DeferredCommand
    is_fix: bool = False
    append_files: bool = True
    filter_key: str = ""
    extra_filters: tuple[str, ...] = field(default_factory=tuple)
    ignore_exit: bool = False
    description: str = ""
    failure_on_output_regex: str | None = None
    timeout_s: float | None = None
    env: dict[str, str] = field(default_factory=dict)

    def build_cmd(self, files: list[Path], cfg: Config, root: Path) -> list[str]:
        out = list(self.cmd.realize(cfg, root))
        if self.append_files and files:
            out += [str(p) for p in files]
        return out

    @property
    def out_filter(self) -> OutputFilter:
        return OutputFilter(list(self.extra_filters))


@dataclass
class TextParserConfig:
    """Configuration for parsing plain text output."""

    regex: re.Pattern[str]
    sev_from: str


class Parser(Protocol):
    """An abstraction for parsing tool output into diagnostics."""

    def parse(self, payload: Any) -> list[Diagnostic]: ...


class JsonParser:
    """A concrete parser for JSON output, implementing the Parser protocol."""

    def __init__(self, transform_func: Callable[[Any, str], list[RawDiagnostic]], tool_name: str):
        self.transform_func = transform_func
        self.tool_name = tool_name

    def parse(self, payload: Any) -> list[Diagnostic]:
        try:
            records = self.transform_func(payload, self.tool_name)
            return [_map_to_diagnostic(rec) for rec in records]
        except Exception:
            # This block handles cases where the transform function fails,
            # which can happen if a tool's output is already a list of Diagnostic objects.
            # We'll safely check and return it if it matches the expected type.
            if not isinstance(payload, list):
                return []

            diagnostics: list[Diagnostic] = []
            for item in payload:
                if isinstance(item, Diagnostic):
                    diagnostics.append(item)
            return diagnostics


class TextParser:
    """A concrete parser for plain text output, implementing the Parser protocol."""

    def __init__(self, config: TextParserConfig, tool_name: str):
        self.config = config
        self.tool_name = tool_name
        self.regex = config.regex

    def parse(self, payload: Any) -> list[Diagnostic]:
        if not isinstance(payload, str):
            return []

        # New logic to select the correct text transformer
        raw_diags: list[RawDiagnostic]
        if self.tool_name in {"clippy", "cargo-test", "cargo-fmt", "rust"}:
            raw_diags = transform_text_rust(payload)
        else:
            raw_diags = transform_text_regex(payload, self.tool_name, self.regex)

        return [_map_to_diagnostic(rec) for rec in raw_diags]


class CompositeParser:
    """A parser that holds and can choose between a JSON and a text parser."""

    def __init__(self, json_parser: Parser | None = None, text_parser: Parser | None = None):
        self.json_parser = json_parser
        self.text_parser = text_parser

    def parse(self, payload: Any) -> list[Diagnostic]:
        # This parse method is a placeholder; the main logic in `run_tool` will select which parser to use.
        if self.json_parser:
            return self.json_parser.parse(payload)
        if self.text_parser:
            return self.text_parser.parse(payload)
        return []


class Runner(Protocol):
    """An abstraction for how to prepare and execute a tool's command."""

    def build_cmd(self, args: BuildCmdArgs) -> list[str]: ...


class DefaultRunner:
    """The default runner for standard commands."""

    def build_cmd(self, args: BuildCmdArgs) -> list[str]:
        return args.action.build_cmd(args.files, args.cfg, args.root)


class PythonRunner:
    """A runner for Python tools that may require venv wrapping and special handling."""

    def build_cmd(self, args: BuildCmdArgs) -> list[str]:
        cmd = args.action.build_cmd(args.files, args.cfg, args.root)
        # Check if the command is for pylint to apply special handling
        if "pylint" in Path(cmd[0]).name:
            if plugs := detect_pylint_plugins():
                cmd = cmd[:1] + ["--load-plugins", ",".join(plugs)] + cmd[1:]
        return _maybe_wrap_python_cmd(cmd)


@dataclass
class Tool:
    name: str
    actions: list[ToolAction]
    languages: tuple[str, ...] = field(default_factory=tuple)
    file_extensions: tuple[str, ...] = field(default_factory=tuple)
    optional: bool = True
    runner: Runner = field(default_factory=DefaultRunner)
    special_handling: str | None = None
    run_on_project_if_no_files: bool = False
    # New fields for consolidated configuration
    output_filters: tuple[str, ...] = field(default_factory=tuple)
    parser: Parser | None = None
    config_files: tuple[str, ...] = field(default_factory=tuple)
    force_json_for_diags: bool = False

    def is_available(self) -> bool:
        if not self.actions:
            return False
        return which(self.actions[0].cmd.base_cmd[0]) is not None

    def select_files(self, files: list[Path]) -> list[Path]:
        return [f for f in files if (not self.file_extensions or f.suffix in self.file_extensions)]


def _looks_like_node_command(executable: str) -> bool:
    name = Path(executable).name.lower()
    return any(name == hint or name.startswith(f"{hint}.") for hint in NODE_EXECUTABLE_HINTS)


def _ensure_npx_noninteractive(cmd: list[str]) -> list[str]:
    if not cmd:
        return cmd
    exe = Path(cmd[0]).name.lower()
    if exe != "npx":
        return cmd
    flags = {arg for arg in cmd[1:] if arg.startswith("-")}
    extras: list[str] = []
    if not ({"--yes", "-y"} & flags):
        extras.append("--yes")
    if "--no-install" not in flags:
        extras.append("--no-install")
    if not extras:
        return cmd
    return [cmd[0], *extras, *cmd[1:]]


def _find_local_node_binary(tool_name: str, files: Iterable[Path]) -> Path | None:
    suffixes = ("", ".cmd", ".ps1", ".exe")
    seen: set[Path] = set()

    def check_dir(directory: Path) -> Path | None:
        node_bin = directory / "node_modules" / ".bin"
        for suff in suffixes:
            candidate = node_bin / f"{tool_name}{suff}"
            if candidate.exists():
                return candidate
        return None

    for candidate_path in files:
        current = candidate_path if candidate_path.is_dir() else candidate_path.parent
        while True:
            current = current.resolve()
            if current in seen:
                break
            seen.add(current)
            if local := check_dir(current):
                return local
            if current == ROOT or current.parent == current:
                break
            current = current.parent

    if local := check_dir(ROOT):
        return local
    return None


def _normalize_command(cmd: list[str], files: list[Path]) -> tuple[list[str], dict[str, str] | None]:
    normalized = list(cmd)
    env_overrides: dict[str, str] = {}
    if normalized:
        exe = normalized[0]
        if Path(exe).name.lower() == "npx":
            tool_arg_idx = None
            for idx, token in enumerate(normalized[1:], start=1):
                if not token.startswith("-"):
                    tool_arg_idx = idx
                    break
            if tool_arg_idx is not None:
                tool_name = Path(normalized[tool_arg_idx]).name
                if local_bin := _find_local_node_binary(tool_name, files):
                    normalized = [str(local_bin), *normalized[tool_arg_idx + 1 :]]
                else:
                    normalized = _ensure_npx_noninteractive(normalized)
        if _looks_like_node_command(normalized[0]):
            for key, value in NODE_ENV_DEFAULTS.items():
                env_overrides.setdefault(key, value)

    return normalized, (env_overrides or None)


@lru_cache(maxsize=512)
def _cached_source_lines(path_str: str) -> tuple[str, ...]:
    try:
        text = Path(path_str).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ()
    return tuple(text.splitlines())


def _scan_python_symbols(lines: tuple[str, ...]) -> list[tuple[int, str]]:
    records: list[tuple[int, str]] = []
    stack: list[tuple[int, str]] = []
    for lineno, raw_line in enumerate(lines, start=1):
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if m_cls := _PY_CLASS_RE.match(raw_line):
            stack.append((indent, m_cls.group("name")))
            continue
        if m_def := _PY_DEF_RE.match(raw_line):
            qual = [entry[1] for entry in stack] + [m_def.group("name")]
            records.append((lineno, ".".join(qual)))
    return records


def _scan_typescript_symbols(lines: tuple[str, ...]) -> list[tuple[int, str]]:
    records: list[tuple[int, str]] = []
    class_stack: list[tuple[int, str]] = []
    brace_depth = 0
    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        class_match = _TS_CLASS_RE.match(raw_line)
        func_name: str | None = None
        if not stripped or stripped.startswith("//"):
            open_braces = raw_line.count("{")
            close_braces = raw_line.count("}")
            brace_depth += open_braces - close_braces
            while class_stack and brace_depth < class_stack[-1][0]:
                class_stack.pop()
            if class_match:
                class_stack.append((brace_depth, class_match.group("name")))
            continue
        if m := _TS_FUNC_RE.match(raw_line):
            func_name = m.group("name")
        elif m := _TS_CONST_FUNC_RE.match(raw_line):
            func_name = m.group("name")
        elif class_stack and (m := _TS_METHOD_RE.match(raw_line)):
            func_name = m.group(1)
        if func_name:
            prefix = ".".join(name for _, name in class_stack)
            symbol = f"{prefix}.{func_name}" if prefix else func_name
            records.append((lineno, symbol))
        open_braces = raw_line.count("{")
        close_braces = raw_line.count("}")
        brace_depth += open_braces - close_braces
        while class_stack and brace_depth < class_stack[-1][0]:
            class_stack.pop()
        if class_match:
            class_stack.append((brace_depth, class_match.group("name")))
    return records


@lru_cache(maxsize=512)
def _symbol_index(path_str: str) -> tuple[tuple[int, str], ...]:
    lines = _cached_source_lines(path_str)
    if not lines:
        return ()
    suffix = Path(path_str).suffix.lower()
    if suffix == ".py":
        records = _scan_python_symbols(lines)
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        records = _scan_typescript_symbols(lines)
    else:
        records = []
    return tuple(records)


def _resolve_source_path(file_name: str | None) -> Path | None:
    if not file_name:
        return None
    candidate = Path(file_name)
    possible: list[Path] = []
    if candidate.is_absolute():
        possible.append(candidate)
    else:
        possible.extend([candidate, ROOT / candidate])
    for option in possible:
        try:
            if option.exists():
                return option.resolve()
        except Exception:
            continue
    try:
        return candidate.resolve()
    except Exception:
        return None


def _symbol_for_location(file_name: str | None, line: int | None) -> str | None:
    if not file_name or not isinstance(line, int) or line <= 0:
        return None
    path = _resolve_source_path(file_name)
    if not path:
        return None
    entries = _symbol_index(str(path))
    symbol: str | None = None
    for entry_line, entry_symbol in entries:
        if entry_line > line:
            break
        symbol = entry_symbol
    return symbol


@dataclass
class ToolOutcomeStep:
    action: str
    rc: int
    stdout: str
    stderr: str
    raw_stdout: str = ""
    raw_stderr: str = ""
    diagnostics: list[Diagnostic] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    cached: bool = False


@dataclass
class ToolOutcome:
    suite: str
    tool: str
    failed: bool
    steps: list[ToolOutcomeStep] = field(default_factory=list)
    crashed: bool = False
    crash_reason: str = ""


@dataclass
class ReportSummary:
    failed_tools: int
    skipped_missing: int
    total_tools: int


@dataclass
class ToolReport:
    failed: bool
    steps: list[ToolOutcomeStep]


@dataclass
class Report:
    version: int
    files_scanned: int
    suites: dict[str, dict[str, ToolReport]]
    summary: ReportSummary


@dataclass
class JsonlRecord:
    file: str
    line: int
    col: int
    severity: str
    group: str
    tool: str
    code: str | None
    message: str
    fingerprint: str


@dataclass
class SarifArtifactLocation:
    uri: str


@dataclass
class SarifRegion:
    start_line: int
    start_column: int


@dataclass
class SarifPhysicalLocation:
    artifact_location: SarifArtifactLocation
    region: SarifRegion


@dataclass
class SarifLocation:
    physical_location: SarifPhysicalLocation


@dataclass
class SarifMessage:
    text: str


@dataclass
class SarifResult:
    rule_id: str
    level: str
    message: SarifMessage
    locations: list[SarifLocation]


@dataclass
class SarifRule:
    id: str
    name: str
    short_description: SarifMessage
    help_uri: str | None
    default_configuration: dict[str, Any]


@dataclass
class SarifTool:
    driver: dict[str, Any]


@dataclass
class SarifRun:
    tool: SarifTool
    results: list[SarifResult]


@dataclass
class SarifReport:
    schema: str
    version: str
    runs: list[SarifRun]


@dataclass
class LanguageSuite:
    name: str
    detector: Callable[[Path], bool]
    tools_factory: Callable[[Path], list[Tool]]


class ToolException(Exception):
    """Custom exception to wrap tool crashes with context."""

    def __init__(self, tool_name: str, original_exc: Exception):
        self.tool_name = tool_name
        self.original_exc = original_exc
        super().__init__(f"[{tool_name}] crashed: {original_exc}")


@dataclass
class GhaAnnotation:
    """Represents a GitHub Actions annotation."""

    kind: Literal["error", "warning", "notice"]
    message: str
    file: str | None = None
    line: int | None = None
    col: int | None = None
    title: str | None = None


@dataclass
class ToolRunContext:
    """Context for running a single tool or a suite of tools."""

    suite_name: str
    files: list[Path]
    workspace_path: Path
    exec_cfg: ExecutionConfig
    output_cfg: OutputConfig
    cfg: Config


@dataclass
class BuildCmdArgs:
    """Arguments for building a tool command."""

    action: ToolAction
    files: list[Path]
    cfg: Config
    root: Path


@dataclass
class RunToolArgs:
    """Arguments for running a single tool."""

    tool: Tool
    ctx: ToolRunContext


@dataclass
class CacheKeyArgs:
    """Arguments for generating a cache key."""

    cmd: list[str]
    files: list[Path]
    version: str
    config_hash: str


@dataclass
class CacheLoadArgs:
    """Arguments for loading from cache."""

    cache_dir: Path
    key: str
    files: list[Path]


@dataclass
class CacheSaveArgs:
    """Arguments for saving to cache."""

    cache_dir: Path
    key: str
    files: list[Path]
    payload: CachePayload


@dataclass
class Workspace:
    """Represents a logical project workspace within the repository."""

    path: Path
    languages: set[str]
    markers: set[str] = field(default_factory=set)
    files: list[Path] = field(default_factory=list)

    def display_name(self) -> str:
        try:
            rel = str(self.path.resolve().relative_to(TOP_ROOT.resolve()))
        except Exception:
            rel = str(self.path)
        return rel or "."


@dataclass
class LintingContext:
    """Context for a full linting run across workspaces."""

    workspaces: list[Workspace]
    all_files: list[Path]
    suites: list[LanguageSuite]
    exec_cfg: ExecutionConfig
    output_cfg: OutputConfig
    file_cfg: FileDiscoveryConfig
    cfg: Config


SUITES: list[LanguageSuite] = []


def register_suite(suite: LanguageSuite) -> None:
    SUITES.append(suite)


# --- Central Tool Definitions ---

ALL_TOOLS: list[Tool] = []


def register_tool(tool: Tool) -> None:
    ALL_TOOLS.append(tool)


# Prettier - defined once, used across suites
register_tool(
    Tool(
        name="prettier",
        actions=[
            ToolAction(
                "write",
                DeferredCommand(["npx", "prettier", "--write"], "prettier"),
                is_fix=True,
                ignore_exit=True,
                timeout_s=180.0,
            ),
            ToolAction(
                "check",
                DeferredCommand(["npx", "prettier", "--check"], "prettier"),
                timeout_s=180.0,
            ),
        ],
        languages=("python", "javascript", "markdown"),
        file_extensions=(
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".json",
            ".css",
            ".md",
            ".mdx",
            ".yml",
            ".yaml",
        ),
        output_filters=(r"^All matched files use Prettier code style!$",),
        config_files=(".prettierrc*", "prettier.config.*"),
    )
)


# ---------------- GitHub annotations ----------------
def _gha_escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _camel_case(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class SarifEncoder(json.JSONEncoder):
    """A custom JSON encoder to convert snake_case to camelCase for SARIF."""

    def default(self, o: Any) -> Any:
        if hasattr(o, "__dict__"):
            return {
                _camel_case(k): v
                for k, v in o.__dict__.items()
                if not (isinstance(v, list) and not v) and v is not None
            }
        return super().default(o)


def _relpath(pth: str) -> str:
    try:
        return str(Path(pth).resolve().relative_to(ROOT.resolve()))
    except Exception:
        return pth


def _gha_emit(annotation: GhaAnnotation) -> None:
    props = []
    if annotation.file:
        props.append(f"file={_gha_escape(_relpath(annotation.file))}")
    if annotation.line is not None:
        props.append(f"line={annotation.line}")
    if annotation.col is not None:
        props.append(f"col={annotation.col}")
    if annotation.title:
        props.append(f"title={_gha_escape(annotation.title)}")
    print(f"::{annotation.kind} {','.join(props)}::{_gha_escape(annotation.message)}")


def transform_json_eslint(payload: Any, _tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw eslint JSON to a standardized list of RawDiagnostics."""
    records = []
    for file_entry in _ensure_list(payload):
        fp = file_entry.get("filePath")
        for m in file_entry.get("messages", []):
            sev = Severity.WARNING if m.get("severity", 2) == 1 else Severity.ERROR
            if m.get("severity") == 0:
                sev = Severity.NOTICE
            records.append(
                RawDiagnostic(
                    file=fp,
                    line=m.get("line") or 1,
                    col=m.get("column") or 1,
                    severity=sev,
                    message=m.get("message", ""),
                    code=m.get("ruleId"),
                    source="eslint",
                )
            )
    return records


def transform_json_ruff(payload: Any, _tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw ruff JSON to a standardized list of RawDiagnostics."""
    return [
        RawDiagnostic(
            file=item.get("filename"),
            line=item.get("row") or 1,
            col=item.get("col") or 1,
            severity=Severity.WARNING,  # Ruff doesn't provide severity in JSON
            message=item.get("message", ""),
            code=item.get("code"),
            source="ruff",
        )
        for item in _ensure_list(payload)
    ]


def transform_json_mypy(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw mypy JSON to a standardized list of RawDiagnostics."""
    records = []
    for item in _ensure_list(payload):
        sev_str = item.get("severity", "error")
        sev = Severity(sev_str) if sev_str in Severity.__members__.values() else Severity.NOTICE
        records.append(
            RawDiagnostic(
                file=item.get("path") or item.get("filename"),
                line=item.get("line") or 1,
                col=item.get("column") or 1,
                severity=sev,
                message=item.get("message", ""),
                code=item.get("code"),
                source=tool_name,
            )
        )
    return records


def _pylint_type_to_severity(pylint_type: str) -> Severity:
    """Converts a pylint message type string to a Severity enum."""
    typ = (pylint_type or "").lower()
    if typ in {"error", "fatal"}:
        return Severity.ERROR
    if typ in {"refactor", "convention", "info"}:
        return Severity.NOTICE
    return Severity.WARNING


def transform_json_pylint(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw pylint JSON to a standardized list of RawDiagnostics."""
    records = []
    for item in _ensure_list(payload):
        sev = _pylint_type_to_severity(item.get("type", ""))
        records.append(
            RawDiagnostic(
                file=item.get("path") or item.get("filename"),
                line=item.get("line") or 1,
                col=item.get("column") or 1,
                severity=sev,
                message=item.get("message", ""),
                code=item.get("message-id") or item.get("symbol"),
                source=tool_name,
            )
        )
    return records


def transform_json_pyright(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw pyright JSON to a standardized list of RawDiagnostics."""
    records = []
    arr = payload.get("generalDiagnostics", []) if isinstance(payload, dict) else []
    for d in arr:
        rng = d.get("range") or {}
        start = rng.get("start") or {}
        sev_str = d.get("severity", "error")
        sev = Severity.NOTICE if sev_str == "information" else Severity(sev_str)
        records.append(
            RawDiagnostic(
                file=d.get("file"),
                line=(start.get("line") or 0) + 1,
                col=(start.get("character") or 0) + 1,
                severity=sev,
                message=d.get("message", ""),
                code=d.get("rule"),
                source=tool_name,
            )
        )
    return records


def transform_json_bandit(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw bandit JSON to a standardized list of RawDiagnostics."""
    records = []
    res = payload.get("results", []) if isinstance(payload, dict) else []
    for r in res:
        sev_str = (r.get("issue_severity") or "MEDIUM").lower()
        sev = (
            Severity.ERROR
            if sev_str in {"high", "critical"}
            else (Severity.WARNING if sev_str in {"medium"} else Severity.NOTICE)
        )
        records.append(
            RawDiagnostic(
                file=r.get("filename"),
                line=r.get("line_number") or 1,
                col=1,
                severity=sev,
                message=r.get("issue_text", ""),
                code=r.get("test_id"),
                source=tool_name,
            )
        )
    return records


def transform_json_golangci(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw golangci-lint JSON to a standardized list of RawDiagnostics."""
    diags: list[RawDiagnostic] = []
    issues = payload.get("Issues") or payload.get("issues") or []
    for it in issues:
        pos = it.get("Pos") or {}
        fp = pos.get("Filename") or it.get("file")
        line = pos.get("Line") or it.get("line") or 1
        col = pos.get("Column") or it.get("column") or 1
        sev_str = (it.get("Severity") or it.get("severity") or "warning").lower()
        msg = f"{it.get('FromLinter') or it.get('source') or ''} {it.get('Text') or it.get('message') or ''}".strip()
        if sev_str not in ("error", "warning", "notice"):
            sev_str = "warning"
        diags.append(
            RawDiagnostic(
                file=fp,
                line=line,
                col=col,
                severity=Severity(sev_str),
                message=msg,
                code=it.get("FromLinter") or it.get("source"),
                source=tool_name,
            )
        )
    return diags


def transform_text_rust(payload: Any) -> list[RawDiagnostic]:
    """Transforms raw rustc/cargo text output to a standardized list of RawDiagnostics."""
    diags: list[RawDiagnostic] = []
    lines = (payload if isinstance(payload, str) else "").splitlines()
    last_sev, last_msg = None, None
    for raw in lines:
        if not (line := raw.strip()):
            continue
        if mfmt := _RE_RUSTFMT_DIFF.match(line):
            diags.append(
                RawDiagnostic(
                    file=mfmt.group("file"),
                    line=int(mfmt.group("line")),
                    col=int(mfmt.group("col")),
                    severity=Severity.WARNING,
                    message="rustfmt wants changes",
                    code=None,
                    source="cargo-fmt",
                )
            )
        elif "panicked at" in line:
            if mp := _RE_RUST_PANIC_AT.search(line):
                diags.append(
                    RawDiagnostic(
                        file=mp.group("file"),
                        line=int(mp.group("line")),
                        col=int(mp.group("col")),
                        severity=Severity.ERROR,
                        message=line,
                        code="panic",
                        source="rust",
                    )
                )
        elif line.startswith("warning: "):
            last_sev, last_msg = "warning", line[len("warning: ") :]
        elif line.startswith("error: "):
            last_sev, last_msg = "error", line[len("error: ") :]
        elif mloc := _RE_RUST_LOC.match(line):
            if last_sev:
                diags.append(
                    RawDiagnostic(
                        file=mloc.group("file"),
                        line=int(mloc.group("line")),
                        col=int(mloc.group("col")),
                        severity=Severity(last_sev),
                        message=last_msg or "",
                        code=None,
                        source="rust",
                    )
                )
                last_sev, last_msg = None, None
    return diags


def transform_json_cargo(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw cargo/clippy JSON to a standardized list of RawDiagnostics."""
    diags: list[RawDiagnostic] = []
    items: list[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, str):
        for line_str in payload.splitlines():
            if not (json_line_str := line_str.strip()):
                continue
            try:
                items.append(json.loads(json_line_str))
            except Exception:
                continue
    elif isinstance(payload, dict):
        items = [payload]

    for it in items:
        msg = it.get("message") or {}
        if not isinstance(msg, dict):
            continue
        level = msg.get("level", "warning")
        sev = Severity.ERROR if level == "error" else (Severity.WARNING if level == "warning" else Severity.NOTICE)
        code_obj = msg.get("code")
        code = code_obj.get("code") if isinstance(code_obj, dict) else None
        if not (spans := msg.get("spans") or []):
            continue
        primary = next((sp for sp in spans if sp.get("is_primary")), spans[0])
        fp = primary.get("file_name")
        line_val = primary.get("line_start")
        line = int(line_val) if isinstance(line_val, int) else 1
        col = primary.get("column_start") or 1
        text = msg.get("message") or ""
        diags.append(
            RawDiagnostic(
                file=fp,
                line=line,
                col=col,
                severity=sev,
                message=text,
                code=code,
                source=tool_name,
            )
        )
    return diags


def transform_text_tsc(payload: Any, tool_name: str) -> list[RawDiagnostic]:
    """Transforms raw tsc text output to a standardized list of RawDiagnostics."""
    s = payload if isinstance(payload, str) else ""
    records: list[RawDiagnostic] = []
    for line in s.splitlines():
        if not (m := _RE_TSC.match(line.strip())):
            continue
        gd = m.groupdict()
        sev_str = gd.get("sev", "error")
        code = gd.get("code")
        msg = gd.get("msg") or ""
        records.append(
            RawDiagnostic(
                file=gd.get("file"),
                line=int(gd.get("line") or 1),
                col=int(gd.get("col") or 1),
                severity=Severity(sev_str),
                message=((code + " ") if code else "") + msg,
                code=code,
                source=tool_name,
            )
        )
    return records


def _ensure_list(obj: Any) -> list[Any]:
    return obj if isinstance(obj, list) else ([obj] if obj is not None else [])


LEN = "120"
ruff_common = [
    "--respect-gitignore",
    "--ignore",
    "F401",
    "--output-format=concise",
    f"--line-length={LEN}",
    "--target-version=py313",
]

register_tool(
    Tool(
        "black",
        [
            ToolAction(
                "write",
                DeferredCommand(["black", "-l", LEN, "-q"], "black"),
                is_fix=True,
                ignore_exit=True,
            ),
            ToolAction(
                "check",
                DeferredCommand(["black", "-l", LEN, "-q"], "black"),
            ),
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        run_on_project_if_no_files=True,
        output_filters=(
            r"^All done! [0-9]+ files? (re)?formatted\.$",
            r"^All done! ✨ .* files? left unchanged\.$",
        ),
        config_files=("pyproject.toml",),
    )
)
register_tool(
    Tool(
        "ruff",
        [
            ToolAction(
                "fix",
                DeferredCommand(
                    ["ruff", "check"] + ruff_common + ["--fix", "--no-unsafe-fixes", "--fix-only", "--silent"],
                    "ruff",
                ),
                is_fix=True,
                ignore_exit=True,
            ),
            ToolAction(
                "check",
                DeferredCommand(
                    ["ruff", "check"] + ruff_common + ["--fix", "--no-unsafe-fixes", "--no-show-fixes", "--quiet"],
                    "ruff",
                ),
            ),
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        run_on_project_if_no_files=True,
        output_filters=(
            r"^Found 0 errors\..*$",
            r"^All checks passed!$",
            r"^.* 0 files? reformatted.*$",
        ),
        parser=CompositeParser(
            json_parser=JsonParser(transform_json_ruff, "ruff"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<code>[A-Z]\d{1,4})\s*(?P<msg>.+)$"
                    ),
                    sev_from="ruff",
                ),
                "ruff",
            ),
        ),
        config_files=("pyproject.toml", "ruff.toml", ".ruff.toml"),
    )
)
register_tool(
    Tool(
        "pyupgrade",
        [
            ToolAction(
                "apply",
                DeferredCommand(["pyupgrade", "--py313-plus"], "pyupgrade"),
                is_fix=True,
                ignore_exit=True,
            )
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
    )
)
isort_base_cmd = [
    "isort",
    "--profile",
    "google",
    "--py",
    "313",
    "--virtual-env",
    ".venv",
    "--remove-redundant-aliases",
    "--ac",
    "--srx",
    "--gitignore",
    "--ca",
    "--cs",
    "-e",
    "-q",
    "-l",
    LEN,
]
register_tool(
    Tool(
        "isort",
        [
            ToolAction(
                "write",
                DeferredCommand(isort_base_cmd, "isort"),
                is_fix=True,
                ignore_exit=True,
            ),
            ToolAction(
                "check",
                DeferredCommand(isort_base_cmd + ["--check-only", "--diff"], "isort"),
            ),
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        output_filters=(
            r"^SUCCESS: .* files? are correctly sorted and formatted\.$",
            r"^Nothing to do\.$",
        ),
        config_files=("pyproject.toml", ".isort.cfg", "setup.cfg"),
    )
)
register_tool(
    Tool(
        "mypy",
        [
            ToolAction(
                "check",
                DeferredCommand(
                    [
                        "mypy",
                        "--exclude-gitignore",
                        "--sqlite-cache",
                        "--strict",
                        "--warn-redundant-casts",
                        "--warn-unused-ignores",
                        "--no-implicit-reexport",
                        "--show-error-codes",
                        "--show-column-numbers",
                        "--warn-unreachable",
                        "--disallow-untyped-decorators",
                        "--disallow-any-generics",
                        "--check-untyped-defs",
                        "--namespace-packages",
                        "--namespace-packages",
                    ],
                    "mypy",
                ),
                append_files=True,
            )
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        output_filters=(r"^Success:.*",),
        parser=CompositeParser(
            json_parser=JsonParser(transform_json_mypy, "mypy"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning|note):\s*(?P<msg>.+)$"
                    ),
                    sev_from="group",
                ),
                "mypy",
            ),
        ),
        config_files=("pyproject.toml", "mypy.ini", ".mypy.ini", "setup.cfg"),
    )
)
register_tool(
    Tool(
        "pylint",
        [
            ToolAction(
                "check",
                DeferredCommand(
                    [
                        "pylint",
                        f"--jobs={os.cpu_count() or 4}",
                        "--bad-functions=print",
                        f"--max-line-length={LEN}",
                        "--max-complexity=15",
                        "--min-similarity-lines=10",
                        "--ignore-long-lines=^\\s*(# )?<?https?://\\S+>?$",
                        "--disable=too-many-try-statements,no-else-return,too-many-public-methods,consider-alternative-union-syntax,line-too-long,missing-module-docstring,missing-class-docstring,missing-function-docstring,too-many-lines,too-complex,too-few-public-methods,too-many-instance-attributes,subprocess-run-check,reimported,import-outside-toplevel,too-many-arguments,too-many-locals,too-many-branches,too-many-statements",
                        "--fail-under=9.5",
                    ],
                    "pylint",
                ),
            )
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        special_handling="pylint_plugins",
        output_filters=(
            r"^Your code has been rated at 10\.00/10.*$",
            r"^----$",
            r"^Your code has been rated.*$",
            r"^$",
            r"^\*\*\*$",
        ),
        parser=CompositeParser(
            json_parser=JsonParser(transform_json_pylint, "pylint"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<code>[CRWEF]\d{4}):\s*(?P<msg>.+)$"
                    ),
                    sev_from="pylint",
                ),
                "pylint",
            ),
        ),
        config_files=("pyproject.toml", ".pylintrc", "pylintrc", "setup.cfg"),
    )
)
register_tool(
    Tool(
        "pyright",
        [
            ToolAction(
                "project",
                DeferredCommand(["pyright", "--verbose"], "pyright"),
                append_files=True,
            )
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        output_filters=(
            r"^No configuration file found\..*",
            r"^Found 0 errors in .* files? \(.*\)$",
        ),
        parser=CompositeParser(
            json_parser=JsonParser(transform_json_pyright, "pyright"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\s*-\s*(?P<sev>error|warning|information)\s*(?P<code>\w+)?:\s*(?P<msg>.+)$"
                    ),
                    sev_from="group",
                ),
                "pyright",
            ),
        ),
        config_files=("pyproject.toml",),
    )
)
register_tool(
    Tool(
        "bandit",
        [
            ToolAction(
                "scan",
                DeferredCommand(["bandit", "-ll"], "bandit"),
            )
        ],
        languages=("python",),
        file_extensions=(".py",),
        runner=PythonRunner(),
        output_filters=(
            r"^Run started:.*$",
            r"^Test results:$",
            r"^No issues identified\.$",
            r"^Files skipped \(.*\):$",
        ),
        parser=CompositeParser(json_parser=JsonParser(transform_json_bandit, "bandit")),
        config_files=("pyproject.toml", ".bandit", "bandit.yml"),
        force_json_for_diags=True,
    )
)
register_tool(
    Tool(
        "pytest",
        [
            ToolAction(
                "smoke",
                DeferredCommand(["pytest", "-q", "-m", "smoke", "-c", "/dev/null"], "pytest"),
                append_files=True,
            )
        ],
        languages=("python",),
        runner=PythonRunner(),
        run_on_project_if_no_files=True,
        output_filters=(
            r"^=+ .* in .*s =+$",
            r"^collected [0-9]+ items$",
            r"^platform .* - Python .*",
            r"^cache cleared$",
        ),
    )
)


register_tool(
    Tool(
        "eslint",
        [
            ToolAction(
                "fix",
                DeferredCommand(["npx", "eslint", "--fix"], "eslint"),
                is_fix=True,
                ignore_exit=True,
                timeout_s=240.0,
            ),
            ToolAction(
                "check",
                DeferredCommand(["npx", "eslint"], "eslint"),
                timeout_s=240.0,
            ),
        ],
        languages=("javascript",),
        file_extensions=(".js", ".jsx", ".ts", ".tsx"),
        output_filters=(r"^✔.*", r"^✨.*", r"^No problems found\..*$"),
        parser=CompositeParser(
            json_parser=JsonParser(transform_json_eslint, "eslint"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\s+-\s+(?P<msg>.+?)(?:\s+\((?P<rule>[^)]+)\))?$"
                    ),
                    sev_from="default",
                ),
                "eslint",
            ),
        ),
        config_files=(".eslintrc", "*.eslintrc*"),
    )
)
register_tool(
    Tool(
        "tsc",
        [
            ToolAction(
                "project",
                DeferredCommand(["npx", "tsc", "--noEmit"], "tsc"),
                append_files=False,
                timeout_s=420.0,
            )
        ],
        languages=("javascript",),
        output_filters=(r"^Found 0 errors\..*$",),
        parser=CompositeParser(
            json_parser=JsonParser(transform_text_tsc, "tsc"),
            text_parser=TextParser(
                TextParserConfig(
                    regex=re.compile(
                        r"^(?P<file>[^:(\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s*(?P<code>[A-Za-z]+\d+)?:?\s*(?P<msg>.+)$"
                    ),
                    sev_from="group",
                ),
                "tsc",
            ),
        ),
        config_files=("tsconfig*.json",),
    )
)
register_tool(
    Tool(
        "jest",
        [
            ToolAction(
                "tests",
                DeferredCommand(["npx", "jest", "--passWithNoTests"], "jest"),
                append_files=False,
                timeout_s=420.0,
            )
        ],
        languages=("javascript",),
        output_filters=(
            r"^No tests found.*$",
            r"^Test Suites: 0.*$",
            r"^Tests:       0.*$",
            r"^Snapshots:   0.*$",
        ),
        config_files=("jest.config.*", "package.json"),
    )
)
register_tool(
    Tool(
        "mdformat",
        [
            ToolAction(
                "write",
                DeferredCommand(["mdformat"], "mdformat"),
                is_fix=True,
                ignore_exit=True,
            ),
            ToolAction(
                "check",
                DeferredCommand(["mdformat", "--check"], "mdformat"),
            ),
        ],
        languages=("markdown",),
        file_extensions=(".md",),
    )
)


# ---------------- Parsers ----------------
_RE_RUST_LOC: Final[re.Pattern[str]] = re.compile(r"^\s*-->\s*(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\s*$")
_RE_RUSTFMT_DIFF: Final[re.Pattern[str]] = re.compile(r"^Diff in (?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)")
_RE_RUST_PANIC_AT: Final[re.Pattern[str]] = re.compile(r"\b(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\b")
_RE_TSC: Final[re.Pattern[str]] = re.compile(
    r"^(?P<file>[^:(\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s*(?P<code>[A-Za-z]+\d+)?:?\s*(?P<msg>.+)$"
)


def _severity_from_code(code: str, default: str = "error") -> Severity:
    if not code:
        return Severity(default)
    if (head := code[0].upper()) in {"E", "F"}:
        return Severity.ERROR
    return Severity.WARNING if head in {"W"} else Severity(default)


SEVERITY_RULES: Final[dict[str, list[tuple[re.Pattern[str], Severity]]]] = {
    "ruff": [(re.compile(r"^(D|N)\d{3,4}"), Severity.NOTICE)],
    "pylint": [
        (re.compile(r"^C\d{4}"), Severity.NOTICE),
        (re.compile(r"^R\d{4}"), Severity.NOTICE),
    ],
}


def apply_severity_rules(tool: str, code_or_msg: str, severity: Severity) -> Severity:
    for pattern, sev in SEVERITY_RULES.get(tool, []):
        if pattern.search(code_or_msg or ""):
            return Severity(sev)
    return severity


def add_custom_rule(spec: str) -> str | None:
    try:
        tool, rest = spec.split(":", 1)
        regex, level_str = rest.rsplit("=", 1)
        level_str = level_str.strip().lower()
        try:
            level = Severity(level_str)
        except ValueError:
            return f"invalid level '{level_str}' in '{spec}'"
        SEVERITY_RULES.setdefault(tool, []).append((re.compile(regex), level))
        return None
    except Exception as e:
        return f"invalid rule '{spec}': {e}"


def _map_to_diagnostic(data: RawDiagnostic) -> Diagnostic:
    """Maps a standardized dictionary to a Diagnostic object, applying enrichment."""
    msg = data.message
    code = data.code
    sev = data.severity if isinstance(data.severity, Severity) else Severity(data.severity)
    tool_name = data.source or "unknown"

    # Apply tool-specific severity rules and message formatting
    if tool_name == "pylint":
        if code and code not in msg:
            msg = f"{code} {msg}"
        sev = apply_severity_rules("pylint", code or msg, sev)
    elif tool_name == "ruff":
        if code and code not in msg:
            msg = f"{code} {msg}"
        sev = apply_severity_rules("ruff", code or msg, Severity.WARNING)

    return Diagnostic(
        file=data.file,
        line=data.line,
        col=data.col,
        severity=sev,
        message=msg.strip(),
        title=tool_name,
        code=code,
    )


def transform_text_regex(payload: Any, tool_name: str, regex: re.Pattern[str]) -> list[RawDiagnostic]:
    """Transforms generic regex-based text output to a standardized list of RawDiagnostics."""
    diags: list[RawDiagnostic] = []
    # Generic fallback regex, now defined locally.
    _re_colon_fallback: Final[re.Pattern[str]] = re.compile(
        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+)$"
    )

    lines = (payload if isinstance(payload, str) else "").splitlines()

    for raw in lines:
        if not (line := raw.strip()):
            continue

        if not (m := regex.match(line)):
            continue

        gd = m.groupdict()
        sev_str = "error"
        if "sev" in gd:
            sev_str_val = gd.get("sev", "error")
            sev_str = "notice" if sev_str_val == "information" else sev_str_val
        elif tool_name in {"pylint", "ruff"}:
            # Severity logic for these is now handled in _map_to_diagnostic
            sev_str = "warning"  # Default to warning, rules will adjust it

        diags.append(
            RawDiagnostic(
                file=gd.get("file"),
                line=int(gd.get("line") or 1),
                col=int(gd.get("col") or 1),
                severity=Severity(sev_str),
                message=gd.get("msg") or line,
                code=gd.get("code"),
                source=tool_name,
            )
        )
    return diags


def emit_gha_annotations(tool: Tool, text: str) -> None:
    # Use the tool's parser directly
    diags: list[Diagnostic] = []
    if tool.parser:
        # We assume text parsing is the fallback for GHA emission
        if text_parser := getattr(tool.parser, "text_parser", None):
            diags = text_parser.parse(text)
    if not diags:
        _gha_emit(
            GhaAnnotation(
                kind="error",
                title=tool.name,
                message=f"{tool.name} reported issues but no file/line diagnostics were parsed.",
            )
        )
        return
    for d in diags:
        kind: Literal["error", "warning", "notice"] = (
            "notice"
            if d.severity in {Severity.NOTICE, Severity.NOTE}
            else ("warning" if d.severity == Severity.WARNING else "error")
        )
        _gha_emit(
            GhaAnnotation(
                kind=kind,
                file=d.file,
                line=d.line,
                col=d.col,
                title=d.title,
                message=d.message or "",
            )
        )


def _json_loads_forgiving(s: str) -> Any | None:
    try:
        return json.loads(s)
    except Exception:
        items = []
        for line in s.splitlines():
            if not (stripped_line := line.strip()):
                continue
            try:
                items.append(json.loads(stripped_line))
            except Exception:
                pass
        if items:
            return items
    return None


def _augment_clippy(cmd: list[str]) -> list[str]:
    new = list(cmd)
    if "--" in new:
        idx = new.index("--")
        return new[:idx] + ["--message-format=json"] + new[idx:]
    return new + ["--message-format=json"]


@dataclass
class AnnotationFormat:
    augment: Callable[[list[str]], list[str]]


ANNOTATION_FORMATS: Final[dict[str, AnnotationFormat]] = {
    "eslint": AnnotationFormat(augment=lambda cmd: cmd + ["-f", "json"]),
    "ruff": AnnotationFormat(
        augment=lambda cmd: ((cmd[:2] + ["--output-format", "json"] + cmd[2:]) if cmd[:2] == ["ruff", "check"] else cmd)
    ),
    "mypy": AnnotationFormat(augment=lambda cmd: cmd + ["--error-format=json"]),
    "pylint": AnnotationFormat(augment=lambda cmd: cmd + ["--output-format=json"]),
    "pyright": AnnotationFormat(augment=lambda cmd: cmd + ["--outputjson"]),
    "bandit": AnnotationFormat(augment=lambda cmd: cmd + ["-f", "json"]),
    "golangci-lint": AnnotationFormat(augment=lambda cmd: cmd + ["-f", "json"]),
    "tsc": AnnotationFormat(augment=lambda cmd: cmd + ["--pretty", "false"]),
    "clippy": AnnotationFormat(augment=_augment_clippy),
    "cargo-test": AnnotationFormat(augment=_augment_clippy),
}

# ---------------- Dedupe across tools ----------------
_SEV_RANK: Final[dict[Severity, int]] = {
    Severity.ERROR: 3,
    Severity.WARNING: 2,
    Severity.NOTICE: 1,
}

_IMPORT_PAT: Final[re.Pattern[str]] = re.compile(
    r"(unable to import|no module named|import[- ]error|could not be resolved|reportMissingImports|cannot find module|module not found|E0401|TS2307)",
    re.I,
)
_UNDEF_PAT: Final[re.Pattern[str]] = re.compile(
    r"(undefined name|name [\"'`][^\"'`]+[\"'`] is not defined|reportUndefinedVariable|cannot find name|is not defined|F821|E0602|no-undef|TS(2304|2552))",
    re.I,
)
_UNUSED_IMPORT_PAT: Final[re.Pattern[str]] = re.compile(
    r"(unused import|F401|W0611|import/no-unresolved:\s*\bignored\b)", re.I
)


def _norm_path(file: str | None) -> str:
    if not file:
        return ""
    try:
        return str(Path(file).resolve().relative_to(ROOT.resolve()))
    except (ValueError, TypeError):
        return str(file)


def _extract_token(msg: str) -> str | None:
    if not msg:
        return None
    token = None
    if m := re.search(r'["\'`](.*?)["\'`]', msg):
        if m.group(1):
            token = m.group(1).strip()
    if not token:
        if m := re.search(r"(?:import|module)\s+([A-Za-z0-9_./-]+)", msg, re.I):
            token = m.group(1).strip()
    return token


_GROUP_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "import": _IMPORT_PAT,
    "undefined": _UNDEF_PAT,
    "unused-import": _UNUSED_IMPORT_PAT,
    "unused-variable": re.compile(r"(unused variable|F841|W0612|no-unused-vars|TS6133)", re.I),
    "type": re.compile(
        r"(incompatible type|typed? mismatch|not assignable|reportGeneralTypeIssues|TS(2322|2345|2532|18047))",
        re.I,
    ),
    "syntax": re.compile(
        r"(syntaxerror|parse error|invalid syntax|unexpected token|TS1005|TS1002|TS1128)",
        re.I,
    ),
    "attribute": re.compile(
        r"(has no attribute|member .* does not exist|object has no attribute|reportOptionalMemberAccess)",
        re.I,
    ),
    "style": re.compile(
        r"(pep8|naming|convention|whitespace|line too long|trailing whitespace|N\d{3}|D\d{3}|E\d{3}|W\d{3}|C\d{4}|RUF\d{3}|prettier|format)",
        re.I,
    ),
    "formatting": re.compile(
        r"(formatted|reformatted|would reformat|isort|black|prettier|gofmt|rustfmt)",
        re.I,
    ),
    "security": re.compile(
        r"(bandit|B\d{3}|hardcoded password|injection|pickle|yaml\.load|subprocess\.|shell=)",
        re.I,
    ),
    "deadcode": re.compile(r"(vulture|unused code|unreachable code|dead code)", re.I),
    "complexity": re.compile(r"(too many branches|too complex|cyclomatic|C901|R(126|127|1702|1720))", re.I),
    "performance": re.compile(
        r"(perf|performance|inefficient|unnecessary list comprehension|unnecessary call)",
        re.I,
    ),
    "test-failure": re.compile(
        r"(assert.*failed|FAILED \[|E +|F +|panicked at|AssertionError|test result: FAILED|jest.*failed)",
        re.I,
    ),
}


def _code_prefix_group(tool: str, code: str | None) -> str | None:
    if not code:
        return None
    c = (code or "").upper()
    if tool == "ruff":
        if c.startswith("F401"):
            return "unused-import"
        if c.startswith("F841"):
            return "unused-variable"
        if c.startswith("F821"):
            return "undefined"
        if c.startswith("PERF"):
            return "performance"
        if c[:1] in {"D", "N", "E", "W"}:
            return "style"
        if c.startswith("S"):
            return "security"
        if c.startswith("C90"):
            return "complexity"
    if tool == "pylint":
        if c.startswith("E0401"):
            return "import"
        if c.startswith("E0602"):
            return "undefined"
        if c.startswith("W0611"):
            return "unused-import"
        if c.startswith("W0612"):
            return "unused-variable"
        if c.startswith("R"):
            return "complexity"
        if c.startswith("C"):
            return "style"
    if tool == "eslint":
        if c == "no-unused-vars":
            return "unused-variable"
        if c == "no-undef":
            return "undefined"
        if c == "import/no-unresolved":
            return "import"
    if tool == "bandit":
        return "security"
    if tool == "vulture":
        return "deadcode"
    return None


def _classify_issue(tool: str, code: str | None, message: str) -> str:
    if g := _code_prefix_group(tool, code):
        return g
    text = f"{code or ''} {message or ''}"
    for name, pattern in _GROUP_PATTERNS.items():
        if pattern.search(text):
            return name

    tool_group_map = {
        "black": "formatting",
        "isort": "formatting",
        "prettier": "formatting",
        "gofmt": "formatting",
        "cargo-fmt": "formatting",
        "pytest": "test-failure",
        "jest": "test-failure",
        "cargo-test": "test-failure",
        "gotest": "test-failure",
    }
    return tool_group_map.get(tool.lower(), "generic")


def _norm_msg(msg: str) -> str:
    s = (msg or "").lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s./-]+", "", s)
    return s.strip()


def _tool_rank(tool: str, prefer: list[str]) -> int:
    tool = (tool or "").lower()
    try:
        return prefer.index(tool)
    except ValueError:
        return len(prefer) + 100


def dedupe_outcomes(outcomes: list[ToolOutcome], cfg: DedupeConfig) -> list[ToolOutcome]:
    flat: list[FlatDiagnostic] = []
    seq = 0
    for o in outcomes:
        for si, s in enumerate(o.steps):
            for i, d in enumerate(s.diagnostics or []):
                flat.append((o.suite, o.tool, si, i, d, seq))
                seq += 1
    if not flat:
        return outcomes

    winners = {}
    prefer = [t.lower() for t in (cfg.dedupe_prefer or [])]
    fuzz = max(0, int(cfg.dedupe_line_fuzz))

    def make_key(d: Diagnostic) -> tuple[str, str, str, str, int]:
        file = _norm_path(d.file)
        cls = _classify_issue(d.title, d.code, d.message)
        token = _extract_token(d.message)
        base = (cls, token or "", file if cfg.dedupe_same_file_only else "")
        line = d.line or 1
        bucket = line // (fuzz + 1) if fuzz > 0 else line
        if cls == "generic" and token is None:
            return base + (_norm_msg(d.message or "")[:64], bucket)
        return base + ("", bucket)

    def better(idx_new: int, idx_old: int) -> bool:
        (_, tool_new, _, _, d_new, seq_new) = flat[idx_new]
        (_, tool_old, _, _, d_old, seq_old) = flat[idx_old]
        if cfg.dedupe_by == "first":
            return seq_new < seq_old
        if cfg.dedupe_by == "severity":
            rn = _SEV_RANK.get(d_new.severity, 0)
            ro = _SEV_RANK.get(d_old.severity, 0)
            return (rn, -seq_new) > (ro, -seq_old)
        if cfg.dedupe_by == "prefer":
            rn = _tool_rank(tool_new, prefer)
            ro = _tool_rank(tool_old, prefer)
            return (rn, seq_new) < (ro, seq_old)
        return seq_new < seq_old

    for i, flat_item in enumerate(flat):
        if (key := make_key(flat_item[4])) not in winners:
            winners[key] = i
        elif better(i, winners[key]):
            winners[key] = i

    to_keep = set()
    for idx in winners.values():
        suite, tool, si, di, _, _ = flat[idx]
        to_keep.add((suite, tool, si, di))

    for o in outcomes:
        for si, s in enumerate(o.steps):
            s.diagnostics = [d for i, d in enumerate(s.diagnostics or []) if (o.suite, o.tool, si, i) in to_keep]
    return outcomes


# ---------------- Pretty output & artifacts ----------------
@dataclass
class ProcessingContext:
    """Context for processing results and generating artifacts."""

    outcomes: list[ToolOutcome]
    files: list[Path]
    output_cfg: OutputConfig
    dedupe_cfg: DedupeConfig
    exec_cfg: ExecutionConfig


def _attach_group(d: Diagnostic) -> Diagnostic:
    if not d.group:
        d.group = _classify_issue(d.title, d.code, d.message)
    return d


def _deduped_items(outcomes: list[ToolOutcome]) -> list[Diagnostic]:
    items: list[Diagnostic] = []
    for o in outcomes:
        for s in o.steps:
            items.extend(s.diagnostics or [])
    return [_attach_group(d) for d in items]


def _print_diagnostic_line(d: Diagnostic) -> None:
    sev = d.severity
    sev_tag = {
        Severity.ERROR: "[E]",
        Severity.WARNING: "[W]",
        Severity.NOTICE: "[N]",
    }.get(sev, "[W]")
    group = d.group or "generic"
    line = d.line or 1
    col = d.col or 1
    code = d.code or ""
    tool = d.title or ""
    msg = d.message or ""
    line_out = f"  {sev_tag} {group:<14} L{line}:{col:<3} {msg}  ({tool}{' '+code if code else ''})\n"
    sys.stdout.write(line_out)


def _print_raw_tool_failures(outcomes: list[ToolOutcome], cfg: OutputConfig) -> None:
    """Prints raw output for failed tools that have no diagnostics."""
    section("Tool failures (raw)", use_color=cfg.color)
    for o in outcomes:
        if o.failed:
            for s in o.steps:
                if s.rc != 0 and not s.skipped:
                    failure_log = f"[{o.tool}:{s.action}]\n{(s.raw_stdout or s.raw_stderr or s.stdout or s.stderr or '(no output)')}"
                    sys.stdout.write(failure_log + "\n")


def print_concise(outcomes: list[ToolOutcome], cfg: OutputConfig) -> list[Diagnostic]:
    section("Concise Findings", use_color=cfg.color)
    items = sorted(
        _deduped_items(outcomes),
        key=lambda d: (
            _relpath(d.file or ""),
            d.line or 0,
            d.col or 0,
            d.message or "",
        ),
    )
    seen: set[tuple[str, int, int, str, str]] = set()
    unique_items: list[Diagnostic] = []
    for diag in items:
        rel_path = _relpath(diag.file or "")
        key = (
            rel_path,
            diag.line or 0,
            diag.col or 0,
            diag.code or diag.group or "",
            diag.message or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(diag)

    if not unique_items:
        ok("No diagnostics after dedupe.", use_emoji=cfg.emoji)
        return []

    severity_tag = {
        Severity.ERROR: "E",
        Severity.WARNING: "W",
        Severity.NOTICE: "N",
        Severity.NOTE: "N",
    }

    for diag in unique_items:
        rel_path = _relpath(diag.file or "")
        line = diag.line or 1
        col = diag.col or 0
        location = f"{rel_path}:{line}"
        if col:
            location += f":{col}"
        symbol = _symbol_for_location(diag.file, diag.line)
        symbol_part = f" · {symbol}" if symbol else ""
        sev = severity_tag.get(diag.severity, "W")
        tool = diag.title or "unknown"
        key = diag.code or diag.group or "generic"
        message = (diag.message or "").replace("\n", " ").strip()
        line_out = f"{location}{symbol_part} [{sev}] {tool}:{key} - {message}"
        print(line_out)
    return unique_items


def print_pretty_text(outcomes: list[ToolOutcome], cfg: OutputConfig) -> None:
    if not (items := _deduped_items(outcomes)):
        if any(o.failed for o in outcomes):
            _print_raw_tool_failures(outcomes, cfg)
        else:
            ok("No findings 🎉", use_emoji=cfg.emoji)
        return  # Exit early if there are no items to display
    by_sev: dict[Severity, int] = {}
    by_group: dict[str, int] = {}
    for d in items:
        by_sev[d.severity] = by_sev.get(d.severity, 0) + 1
        if g := d.group or _classify_issue(d.title, d.code, d.message):
            by_group[g] = by_group.get(g, 0) + 1
    section("Findings (deduped)", use_color=cfg.color)
    sev_line = " / ".join(
        f"{k.value}:{v}"
        for k, v in sorted(
            by_sev.items(),
            key=lambda x: {
                Severity.ERROR: 0,
                Severity.WARNING: 1,
                Severity.NOTICE: 2,
                Severity.NOTE: 3,
            }.get(x[0], 4),
        )
    )
    grp_line = " / ".join(f"{k}:{v}" for k, v in sorted(by_group.items()))
    info(f"  Severity → {sev_line}", use_emoji=False)
    info(f"  Groups   → {grp_line}", use_emoji=False)

    if cfg.group_by_code:
        # Group by code, then file and line
        sorted_items = sorted(
            items,
            key=lambda x: (
                x.title or "",
                x.code or "",
                _relpath(x.file or ""),
                x.line or 1,
                x.col or 1,
            ),
        )
        for d in sorted_items:
            sev = d.severity
            sev_tag = {
                Severity.ERROR: "[E]",
                Severity.WARNING: "[W]",
                Severity.NOTICE: "[N]",
            }.get(sev, "[W]")
            group = d.group or "generic"
            line = d.line or 1
            col = d.col or 1
            code = d.code or ""
            tool = d.title or ""
            msg = d.message or ""
            file = _relpath(d.file or "")
            line_out = f"  {sev_tag} {group:<14} {file}:{line}:{col:<3} {msg}  ({tool}{' '+code if code else ''})\n"
            sys.stdout.write(line_out)
    else:
        # Original sort by file, then severity and line
        files = sorted({_relpath(x.file or "") for x in items})
        info("  Files    → " + ", ".join(files), use_emoji=False)
        for file in files:
            sys.stdout.write(f" {file}\n")
            file_diags = sorted(
                [x for x in items if _relpath(x.file or "") == file],
                key=lambda x: (
                    {
                        Severity.ERROR: 0,
                        Severity.WARNING: 1,
                        Severity.NOTICE: 2,
                        Severity.NOTE: 3,
                    }.get(x.severity, 4),
                    x.line or 1,
                    x.col or 1,
                    x.group or "",
                    x.title or "",
                ),
            )
            for d in file_diags:
                _print_diagnostic_line(d)


def print_pretty_jsonl(outcomes: list[ToolOutcome]) -> None:
    for d in _deduped_items(outcomes):
        rec = JsonlRecord(
            file=_relpath(d.file or ""),
            line=d.line or 1,
            col=d.col or 1,
            severity=d.severity.value if d.severity else "warning",
            group=d.group or "generic",
            tool=d.title or "",
            code=d.code,
            message=d.message or "",
            fingerprint=hashlib.sha256(
                f"{_relpath(d.file or '')}:{d.line or 0}:{d.col or 0}:{d.group or ''}:{d.code or ''}:{d.message or ''}".encode(),
                usedforsecurity=False,
            ).hexdigest(),
        )
        print(json.dumps(asdict(rec), ensure_ascii=False))


def _md_escape(s: str) -> str:
    return (s or "").replace("|", r"\|").replace("\n", " ").strip()


def print_pretty_markdown(outcomes: list[ToolOutcome]) -> None:
    if not (items := _deduped_items(outcomes)):
        if any(o.failed for o in outcomes):
            print("### Tool failures (raw)")
            for o in outcomes:
                if o.failed:
                    for s in o.steps:
                        if s.rc != 0 and not s.skipped:
                            print(
                                f"**{o.tool}:{s.action}**\n\n````\n{(s.raw_stdout or s.raw_stderr or s.stdout or s.stderr or '(no output)')}\n````\n"
                            )
            return
        print("**No findings 🎉**")
        return
    by_sev: dict[str, int] = {}
    by_group: dict[str, int] = {}
    for d in items:
        by_sev[d.severity.value] = by_sev.get(d.severity.value, 0) + 1
        if g := d.group or _classify_issue(d.title, d.code, d.message):
            by_group[g] = by_group.get(g, 0) + 1
    print("### Lint Summary (deduped)")
    print()
    print("| Severity | Group | File | Line | Col | Tool | Code | Message |")
    print("|---|---|---|---:|---:|---|---|---|")
    for d in sorted(
        items,
        key=lambda x: (
            {
                Severity.ERROR: 0,
                Severity.WARNING: 1,
                Severity.NOTICE: 2,
                Severity.NOTE: 3,
            }.get(x.severity, 4),
            _relpath(x.file or ""),
            x.line or 1,
            x.col or 1,
            x.group or "",
            x.title or "",
        ),
    ):
        print(
            f"| {d.severity.value.upper()} | {d.group or ''} | {_relpath(d.file or '')} | {d.line or 1} | {d.col or 1} | {d.title or ''} | {d.code or ''} | {_md_escape(d.message or '')} |"
        )


def emit_pretty(outcomes: list[ToolOutcome], cfg: OutputConfig) -> None:
    fmt = (cfg.pretty_format or "text").lower()
    if fmt == "jsonl":
        print_pretty_jsonl(outcomes)
    elif fmt == "markdown":
        print_pretty_markdown(outcomes)
    else:
        print_pretty_text(outcomes, cfg)


def outcomes_to_report(outcomes: list[ToolOutcome], *, files_scanned: int, include_raw: bool) -> dict[str, Any]:
    """Converts a list of tool outcomes into a structured dictionary report."""
    suites: dict[str, dict[str, ToolReport]] = {}
    failed_tools = 0
    skipped_missing = 0
    total_tools = 0
    for o in outcomes:
        total_tools += 1
        suite_report = suites.setdefault(o.suite, {})
        steps_out = []
        for s in o.steps:
            step_to_add = (
                ToolOutcomeStep(
                    action=s.action,
                    rc=s.rc,
                    stdout=s.stdout,
                    stderr=s.stderr,
                    diagnostics=s.diagnostics,
                    skipped=s.skipped,
                    skip_reason=s.skip_reason,
                    cached=s.cached,
                )
                if not include_raw
                else s
            )
            steps_out.append(step_to_add)
            if s.skipped and s.skip_reason == "missing executable":
                skipped_missing += 1

        tool_report = ToolReport(failed=o.failed, steps=steps_out)
        suite_report[o.tool] = tool_report
        if o.failed:
            failed_tools += 1

    summary = ReportSummary(
        failed_tools=failed_tools,
        skipped_missing=skipped_missing,
        total_tools=total_tools,
    )
    report = Report(version=1, files_scanned=files_scanned, suites=suites, summary=summary)
    return asdict(report)


_SEVERITY_TO_SARIF_LEVEL: Final[dict[Severity, Literal["error", "warning", "notice"]]] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTICE: "notice",
    Severity.NOTE: "notice",
}


def _sarif_level(sev: Severity) -> Literal["error", "warning", "notice"]:
    return _SEVERITY_TO_SARIF_LEVEL.get(sev, "warning")


def _rule_help_uri(tool: str, code: str | None) -> str | None:
    if not tool:
        return None
    tool = tool.lower()
    c = (code or "").strip()
    if tool == "eslint" and c:
        return f"https://eslint.org/docs/latest/rules/{c}"
    if tool == "ruff":
        return "https://docs.astral.sh/ruff/rules/"
    if tool == "pylint" and c:
        return "https://pylint.readthedocs.io/en/latest/user_guide/messages/messages_overview.html"
    if tool == "mypy":
        if c:
            return "https://mypy.readthedocs.io/en/stable/error_code_list.html#" + c
        return "https://mypy.readthedocs.io/en/stable/error_code_list.html"
    if tool == "pyright":
        return "https://microsoft.github.io/pyright/#/configuration?id=diagnostic-rule-defaults"
    if tool == "bandit":
        return "https://bandit.readthedocs.io/en/latest/"
    if tool == "golangci-lint" and c:
        return f"https://golangci-lint.run/usage/linters/#{c.lower()}"
    if tool in ("tsc", "typescript"):
        return "https://github.com/microsoft/TypeScript/wiki/Errors"
    if tool in ("clippy", "cargo-fmt", "cargo-test"):
        return "https://rust-lang.github.io/rust-clippy/master/"
    return None


def build_sarif(outcomes: list[ToolOutcome]) -> dict[str, Any]:
    results: list[SarifResult] = []
    rules: dict[str, SarifRule] = {}
    for o in outcomes:
        for s in o.steps:
            for d in s.diagnostics or []:
                rule_id = (d.code or "").strip() or o.tool
                results.append(
                    SarifResult(
                        rule_id=rule_id,
                        level=_sarif_level(d.severity),
                        message=SarifMessage(text=d.message or ""),
                        locations=[
                            SarifLocation(
                                physical_location=SarifPhysicalLocation(
                                    artifact_location=SarifArtifactLocation(uri=str(d.file or "")),
                                    region=SarifRegion(
                                        start_line=d.line or 1,
                                        start_column=d.col or 1,
                                    ),
                                )
                            )
                        ],
                    )
                )
                if rule_id not in rules:
                    rules[rule_id] = SarifRule(
                        id=rule_id,
                        name=rule_id,
                        short_description=SarifMessage(text=o.tool),
                        help_uri=_rule_help_uri(o.tool, d.code),
                        default_configuration={"level": _sarif_level(d.severity)},
                    )

    report = SarifReport(
        schema="https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json",
        version="2.1.0",
        runs=[
            SarifRun(
                tool=SarifTool(driver={"name": "lint.py", "rules": list(rules.values())}),
                results=results,
            )
        ],
    )
    # Use asdict for structure, then custom encoder for final JSON
    # The double conversion is to allow the custom encoder to handle dataclasses
    return json.loads(json.dumps(asdict(report), cls=SarifEncoder))  # type: ignore[no-any-return]


# ---------------- Cache ----------------
@dataclass
class FileMeta:
    p: str
    m: int
    s: int


@dataclass
class CachePayload:
    rc: int
    stdout: str
    stderr: str
    raw_stdout: str
    raw_stderr: str
    diagnostics: list[Diagnostic]
    ts: float
    files_meta: list[FileMeta] = field(default_factory=list)


def _prune_cache(cache_dir: Path, *, max_age_sec: int = 3600) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max_age_sec
        for p in cache_dir.glob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def _files_meta(files: list[Path]) -> list[FileMeta]:
    metas = []
    for f in files:
        try:
            st = f.stat()
            metas.append(FileMeta(p=str(f.resolve()), m=st.st_mtime_ns, s=st.st_size))
        except Exception:
            metas.append(FileMeta(p=str(f.resolve()), m=0, s=-1))
    return metas


_VERSION_CACHE: dict[str, str] = {}


def _prog_from_cmd(cmd: list[str]) -> str:
    if not cmd:
        return ""
    if cmd[0] == "uv" and len(cmd) >= 3 and cmd[1] == "run":
        return cmd[2]
    return Path(cmd[0]).name


def _tool_version(cmd: list[str]) -> str:
    if not (prog := _prog_from_cmd(cmd)):
        return ""
    if prog in _VERSION_CACHE:
        return _VERSION_CACHE[prog]
    candidates = {
        "black": ["--version"],
        "ruff": ["--version"],
        "isort": ["--version"],
        "mypy": ["--version"],
        "pylint": ["--version"],
        "pyright": ["--version"],
        "bandit": ["--version"],
        "vulture": ["--version"],
        "pyupgrade": ["--version"],
        "eslint": ["-v"],
        "prettier": ["--version"],
        "tsc": ["-v"],
        "jest": ["--version"],
        "golangci-lint": ["version", "--format", "short"],
        "go": ["version"],
        "cargo": ["--version"],
        "gitleaks": ["version"],
        "trufflehog": ["--version"],
        "pip-audit": ["--version"],
        "safety": ["--version"],
        "npm": ["--version"],
    }
    args = candidates.get(prog, ["--version"])
    try:
        cp = run([prog] + args)
        out = cp.stdout.strip().splitlines()[0] if cp.returncode == 0 and cp.stdout else ""
    except Exception:
        out = ""
    _VERSION_CACHE[prog] = out
    return out


def _config_files_for_tool(tool: str, root: Path) -> list[Path]:
    tool_map = {
        "black": ["pyproject.toml"],
        "ruff": ["pyproject.toml"],
        "isort": ["pyproject.toml"],
        "mypy": ["pyproject.toml", "mypy.ini", "setup.cfg"],
        "pylint": [".pylintrc", "pyproject.toml"],
        "pyright": ["pyproject.toml"],
        "bandit": ["pyproject.toml"],
        "pytest": ["pyproject.toml"],
        "vulture": ["pyproject.toml"],
        "eslint": {"package.json", ".eslintrc*", ".prettierrc*", "prettier.config.*"},
        "prettier": {"package.json", ".prettierrc*", "prettier.config.*"},
        "tsc": ["tsconfig*.json"],
        "jest": {"package.json", "jest.config.*"},
        "golangci-lint": {"go.mod", "go.sum", ".golangci.yml", ".golangci.yaml"},
        "go": ["go.mod"],
        "govet": ["go.mod"],
        "gotest": ["go.mod"],
        "cargo": ["Cargo.toml"],
        "clippy": ["Cargo.toml"],
        "cargo-fmt": ["Cargo.toml"],
        "cargo-test": ["Cargo.toml"],
    }
    pats = tool_map.get(tool.lower(), [])
    paths: list[Path] = []
    for pat in pats:
        if "*" in pat:
            paths.extend(root.glob(pat))
        elif (f := root / pat).exists():
            paths.append(f)
    return paths


def _hash_configs(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(set(paths)):
        try:
            st = p.stat()
            h.update(str(p).encode())
            h.update(str(st.st_mtime_ns).encode())
            h.update(str(st.st_size).encode())
        except Exception:
            h.update(str(p).encode())
            h.update(b"0")
    return h.hexdigest()


def _cache_key(args: CacheKeyArgs) -> str:
    h = hashlib.sha256()
    h.update((args.version or "").encode())
    h.update("\0".join(args.cmd).encode())
    h.update((args.config_hash or "").encode())
    for f in sorted([str(x.resolve()) for x in args.files]):
        h.update(b"\0")
        h.update(f.encode())
    return h.hexdigest()


def _diagnostics_from_dicts(data: list[dict[str, Any]]) -> list[Diagnostic]:
    diags = []
    for d_dict in data:
        sev_val = d_dict.get("severity")
        if sev_val and isinstance(sev_val, str):
            try:
                d_dict["severity"] = Severity(sev_val)
            except ValueError:
                d_dict["severity"] = Severity.WARNING  # Fallback
        diags.append(Diagnostic(**d_dict))
    return diags


def _cache_load(args: CacheLoadArgs) -> CachePayload | None:
    path = args.cache_dir / f"{args.key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    wanted = {m["p"]: (m["m"], m["s"]) for m in data.get("files_meta", [])}
    for f in args.files:
        rp = str(f.resolve())
        try:
            st = f.stat()
            meta = (st.st_mtime_ns, st.st_size)
        except Exception:
            meta = (0, -1)
        if rp not in wanted or wanted[rp] != meta:
            return None

    return CachePayload(
        rc=data.get("rc", 0),
        stdout=data.get("stdout", ""),
        stderr=data.get("stderr", ""),
        raw_stdout=data.get("raw_stdout", ""),
        raw_stderr=data.get("raw_stderr", ""),
        diagnostics=_diagnostics_from_dicts(data.get("diagnostics", [])),
        ts=data.get("ts", 0.0),
        files_meta=[FileMeta(**m) for m in data.get("files_meta", [])],
    )


def _cache_save(args: CacheSaveArgs) -> None:
    try:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        args.payload.files_meta = _files_meta(args.files)
        (args.cache_dir / f"{args.key}.json").write_text(json.dumps(asdict(args.payload)), encoding="utf-8")
    except Exception:
        pass


# ---------------- Runners & Plugins ----------------
def _get_venv_bin_path(root: Path) -> Path | None:
    """Locate .venv/Scripts|bin from *root*, walking up to TOP_ROOT."""
    cur = root.resolve()
    stop = TOP_ROOT.resolve() if "TOP_ROOT" in globals() else cur
    # Create a list of paths to search, from current up to the stop directory
    search_paths = [cur] + list(cur.parents)
    try:
        stop_index = search_paths.index(stop)
        search_paths = search_paths[: stop_index + 1]
    except ValueError:
        pass  # stop not in path, search all the way to filesystem root

    for p in search_paths:
        for name in [".venv", "venv"]:
            v = p / name
            if v.is_dir():
                b = v / ("Scripts" if os.name == "nt" else "bin")
                if b.is_dir():
                    return b
    return None


def python_runner_prefix() -> list[str] | None:
    if which("uv"):
        return ["uv", "run"]
    if _get_venv_bin_path(ROOT):
        return None
    return None


def _maybe_wrap_python_cmd(cmd: list[str]) -> list[str]:
    if (pref := python_runner_prefix()) is not None:
        return pref + cmd
    if vb := _get_venv_bin_path(ROOT):
        exe = cmd[0]
        epath = vb / exe
        if epath.exists():
            return [str(epath)] + cmd[1:]
    return cmd


def detect_pylint_plugins() -> tuple[str, ...]:
    # Unconditional plugins
    plugins: set[str] = {
        "pylint.extensions.bad_builtin",
        "pylint.extensions.broad_try_clause",
        "pylint.extensions.check_elif",
        "pylint.extensions.code_style",
        "pylint.extensions.comparison_placement",
        "pylint.extensions.confusing_elif",
        "pylint.extensions.consider_ternary_expression",
        "pylint.extensions.dict_init_mutate",
        "pylint.extensions.docparams",
        "pylint.extensions.docstyle",
        "pylint.extensions.empty_comment",
        "pylint.extensions.eq_without_hash",
        "pylint.extensions.for_any_all",
        "pylint.extensions.magic_value",
        "pylint.extensions.mccabe",
        "pylint.extensions.overlapping_exceptions",
        "pylint.extensions.redefined_loop_name",
        "pylint.extensions.redefined_variable_type",
        "pylint.extensions.set_membership",
        "pylint.extensions.typing",
        "pylint.extensions.while_used",
        "pylint_htmf",
        "pylint_pydantic",
    }

    def has(mod: str) -> bool:
        try:
            return importlib.util.find_spec(mod) is not None
        except Exception:
            return False

    # Conditional plugins
    conditional_plugins = {
        "django": "pylint_django",
        "celery": "pylint_celery",
        "flask": "pylint_flask",
        "pytest": "pylint_pytest",
        "sqlalchemy": "pylint_sqlalchemy",
        "odoo": "pylint_odoo",
        "quotes": "pylint_quotes",
    }

    final_plugins: set[str] = set(plugins)
    for framework, plugin in conditional_plugins.items():
        if has(framework) and has(plugin):
            final_plugins.add(plugin)

    # Special condition for pylint_venv
    if (ROOT / ".venv").is_dir() and has("pylint_venv"):
        final_plugins.add("pylint_venv")

    return tuple(sorted(final_plugins))


# ---------------- Suites ----------------
def detect_python(root: Path) -> bool:
    return (root / "pyproject.toml").is_file() or any(p.suffix == ".py" for p in root.glob("**/*.py"))


def python_tools(_: Path) -> list[Tool]:
    return [t for t in ALL_TOOLS if "python" in t.languages]


register_suite(LanguageSuite("python", detect_python, python_tools))


def detect_js(root: Path) -> bool:
    return (root / "package.json").is_file() or any(
        p.suffix in {".js", ".jsx", ".ts", ".tsx"} for p in root.glob("**/*.*")
    )


def js_tools(root: Path) -> list[Tool]:
    tools = [t for t in ALL_TOOLS if "javascript" in t.languages]
    # The special logic for multiple tsconfigs remains, but it acts on the filtered list.
    try:
        tsconfigs = [p for p in root.rglob("tsconfig*.json") if "node_modules" not in str(p)]
    except Exception:
        tsconfigs = []
    if tsconfigs:
        for t in tools:
            if t.name == "tsc":
                per_cfg_actions = []
                for cfg_path in tsconfigs:
                    per_cfg_actions.append(
                        ToolAction(
                            name=f"project:{cfg_path}",
                            cmd=DeferredCommand(
                                ["npx", "tsc", "--noEmit", "-p", str(cfg_path)],
                                "tsc",
                            ),
                            append_files=False,
                            filter_key="tsc",
                        )
                    )
                if per_cfg_actions:
                    t.actions = per_cfg_actions
    return tools


register_suite(LanguageSuite("javascript", detect_js, js_tools))


def detect_go(root: Path) -> bool:
    return (root / "go.mod").is_file() or any(p.suffix == ".go" for p in root.glob("**/*.go"))


def go_tools(_: Path) -> list[Tool]:
    return [
        Tool(
            "gofmt",
            [
                ToolAction(
                    "write",
                    DeferredCommand(["gofmt", "-w"], "gofmt"),
                    is_fix=True,
                    filter_key="gofmt",
                    ignore_exit=True,
                ),
                ToolAction(
                    "check",
                    DeferredCommand(["gofmt", "-l"], "gofmt"),
                    filter_key="gofmt",
                    failure_on_output_regex=r".+",
                ),
            ],
            file_extensions=(".go",),
        ),
        Tool(
            "govet",
            [
                ToolAction(
                    "vet",
                    DeferredCommand(["go", "vet"], "govet"),
                    append_files=True,
                    filter_key="govet",
                ),
            ],
        ),
        Tool(
            "golangci-lint",
            [
                ToolAction(
                    "fix",
                    DeferredCommand(["golangci-lint", "run", "--fix"], "golangci-lint"),
                    is_fix=True,
                    append_files=False,
                    filter_key="golangci_lint",
                    ignore_exit=True,
                ),
                ToolAction(
                    "check",
                    DeferredCommand(["golangci-lint", "run"], "golangci-lint"),
                    append_files=False,
                    filter_key="golangci_lint",
                ),
            ],
            config_files=(".golangci.yml", ".golangci.yaml", "go.mod"),
            parser=JsonParser(transform_json_golangci, "golangci-lint"),
        ),
        Tool(
            "gotest",
            [
                ToolAction(
                    "short",
                    DeferredCommand(["go", "test", "./...", "-short"], "gotest"),
                    append_files=False,
                    filter_key="gotest",
                ),
            ],
        ),
    ]


register_suite(LanguageSuite("go", detect_go, go_tools))


def detect_rust(root: Path) -> bool:
    return (root / "Cargo.toml").is_file() or any(p.suffix == ".rs" for p in root.glob("**/*.rs"))


def rust_tools(_: Path) -> list[Tool]:
    # This is a new TextParser we'll use for rust tools.
    rust_text_parser = TextParser(
        TextParserConfig(
            # A dummy regex, as the main logic is in the transformer now.
            regex=re.compile(r".*"),
            sev_from="default",
        ),
        "rust",
    )
    # The JsonParser now uses a dedicated transformer for Rust JSON.
    rust_json_parser = JsonParser(transform_json_cargo, "rust")

    return [
        Tool(
            "cargo-fmt",
            [
                ToolAction(
                    "write",
                    DeferredCommand(["cargo", "fmt"], "cargo-fmt"),
                    is_fix=True,
                    append_files=False,
                    filter_key="cargo_fmt",
                    ignore_exit=True,
                ),
                ToolAction(
                    "check",
                    DeferredCommand(["cargo", "fmt", "--", "--check"], "cargo-fmt"),
                    append_files=False,
                    filter_key="cargo_fmt",
                ),
            ],
            config_files=("Cargo.toml",),
            # Add the parser here
            parser=CompositeParser(
                json_parser=rust_json_parser,
                text_parser=rust_text_parser,
            ),
        ),
        Tool(
            "clippy",
            [
                ToolAction(
                    "check",
                    DeferredCommand(
                        [
                            "cargo",
                            "clippy",
                            "--all-targets",
                            "--all-features",
                            "--",
                            "-D",
                            "warnings",
                        ],
                        "clippy",
                    ),
                    append_files=False,
                    filter_key="clippy",
                )
            ],
            config_files=("Cargo.toml",),
            parser=CompositeParser(
                json_parser=rust_json_parser,
                text_parser=rust_text_parser,
            ),
        ),
        Tool(
            "cargo-test",
            [
                ToolAction(
                    "tests",
                    DeferredCommand(["cargo", "test", "--all-targets", "--quiet"], "cargo-test"),
                    append_files=False,
                    filter_key="cargo_test",
                )
            ],
            parser=CompositeParser(
                json_parser=rust_json_parser,
                text_parser=rust_text_parser,
            ),
        ),
    ]


register_suite(LanguageSuite("rust", detect_rust, rust_tools))


def detect_markdown(root: Path) -> bool:
    return any(p.suffix == ".md" for p in root.glob("**/*.md"))


def markdown_tools(_: Path) -> list[Tool]:
    return [t for t in ALL_TOOLS if "markdown" in t.languages]


register_suite(LanguageSuite("markdown", detect_markdown, markdown_tools))


# Optional security suite (enabled via --lang security or --enable security)
def detect_security(_: Path) -> bool:
    return False


def security_tools(_: Path) -> list[Tool]:
    tools = []
    tools.append(
        Tool(
            "gitleaks",
            [
                ToolAction(
                    "scan",
                    DeferredCommand(["gileaks", "detect", "--no-git"], "gileaks"),
                    filter_key="",
                ),
            ],
            optional=True,
        )
    )
    tools.append(
        Tool(
            "trufflehog",
            [
                ToolAction(
                    "scan",
                    DeferredCommand(["trufflehog", "filesystem", "."], "trufflehog"),
                    filter_key="",
                ),
            ],
            optional=True,
        )
    )
    tools.append(
        Tool(
            "pip-audit",
            [
                ToolAction(
                    "audit",
                    DeferredCommand(["pip-audit", "-r", "requirements.txt"], "pip-audit"),
                    append_files=False,
                    filter_key="",
                ),
            ],
        )
    )
    tools.append(
        Tool(
            "safety",
            [
                ToolAction(
                    "audit",
                    DeferredCommand(["safety", "check", "--full-report"], "safety"),
                    append_files=False,
                    filter_key="",
                ),
            ],
        )
    )
    tools.append(
        Tool(
            "npm-audit",
            [
                ToolAction(
                    "audit",
                    DeferredCommand(["npm", "audit", "--audit-level=moderate"], "npm-audit"),
                    append_files=False,
                    filter_key="",
                ),
            ],
        )
    )
    return tools


register_suite(LanguageSuite("security", detect_security, security_tools))


# ---------------- Misc helpers ----------------
def _count_loc(files: list[Path]) -> int:
    """Counts the total lines of code (LOC) for a list of files."""
    total_lines = 0
    for f in files:
        try:
            total_lines += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
        except Exception:
            pass  # Ignore files that can't be read
    return total_lines


def detect_smoke_enabled() -> bool:
    for p in (ROOT / "tests").rglob("conftest.py"):
        try:
            if "smoke" in p.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    pp = ROOT / "pyproject.toml"
    if pp.is_file():
        try:
            if "smoke" in pp.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    return False


DOC_EXTS: Final[set[str]] = {".md", ".mdx", ".rst", ".txt", ".adoc"}
FRONTEND_DIR_HINTS: Final[set[str]] = {
    "frontend",
    "web",
    "website",
    "ui",
    "client",
    "apps/web",
    "packages/web",
}


def _only_docs(files: list[Path]) -> bool:
    return bool(files) and all((f.suffix.lower() in DOC_EXTS or "docs" in str(f.parent).lower()) for f in files)


def _frontend_only(files: list[Path]) -> bool:
    if not files:
        return False
    hits = 0
    for f in files:
        p = str(f).lower()
        if any(h in p for h in FRONTEND_DIR_HINTS) or f.suffix.lower() in (
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".css",
            ".scss",
            ".vue",
        ):
            hits += 1
        else:
            return False
    return hits > 0


def apply_skip_heuristics(suites: list[LanguageSuite], files: list[Path], cfg: ExecutionConfig) -> list[LanguageSuite]:
    if cfg.force_all:
        return suites
    if _only_docs(files):
        return [s for s in suites if s.name in ("javascript", "markdown")]
    if _frontend_only(files):
        return [s for s in suites if s.name in ("javascript", "security")]
    return suites


def _language_from_extension(path: Path) -> str | None:
    ext = path.suffix.lower()
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if ext in exts:
            return lang
    return None


def discover_workspaces(root: Path, files: list[Path]) -> list[Workspace]:
    marker_lookup = {marker.lower(): lang for lang, markers in LANGUAGE_MARKERS.items() for marker in markers}
    ignore = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
    }
    ignore.update(ALWAYS_EXCLUDE_DIRS)

    root_resolved = root.resolve()
    candidate_info: dict[Path, dict[str, Any]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dn = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in ignore and not d.startswith(".")]
        langs: set[str] = set()
        markers: set[str] = set()
        for fname in filenames:
            lang = marker_lookup.get(fname.lower())
            if lang:
                langs.add(lang)
                markers.add(fname)
        if langs:
            candidate_info[dn.resolve()] = {
                "languages": set(langs),
                "markers": set(markers),
            }

    if root_resolved not in candidate_info:
        candidate_info[root_resolved] = {"languages": set(), "markers": set()}

    workspace_files: dict[Path, list[Path]] = {path: [] for path in candidate_info}
    candidate_paths = sorted(candidate_info.keys(), key=lambda p: len(p.parts), reverse=True)

    for file_path in files:
        try:
            resolved = file_path.resolve()
        except Exception:
            resolved = (root / file_path).resolve()
        owner = root_resolved
        for candidate in candidate_paths:
            if candidate == root_resolved:
                continue
            try:
                resolved.relative_to(candidate)
            except ValueError:
                continue
            else:
                owner = candidate
                break
        workspace_files.setdefault(owner, []).append(file_path)
        if lang := _language_from_extension(file_path):
            candidate_info[owner]["languages"].add(lang)

    workspaces: list[Workspace] = []
    for path, info in candidate_info.items():
        markers = set(info.get("markers", set()))
        languages = set(info.get("languages", set()))
        assigned_files = workspace_files.get(path, [])
        workspaces.append(
            Workspace(
                path=path,
                languages=languages,
                markers=markers,
                files=list(assigned_files),
            )
        )

    def _has_language_files(ws: Workspace, lang: str) -> bool:
        exts = LANGUAGE_EXTENSIONS.get(lang, set())
        if not exts:
            return False
        return any(f.suffix.lower() in exts for f in ws.files)

    for lang in LANGUAGE_EXTENSIONS:
        candidates = [ws for ws in workspaces if lang in ws.languages]
        if len(candidates) <= 1:
            continue
        candidates.sort(key=lambda ws: len(ws.path.parts))
        for idx, ws in enumerate(candidates):
            for child in candidates[idx + 1 :]:
                try:
                    child.path.relative_to(ws.path)
                except ValueError:
                    continue
                marker_names = {marker.lower() for marker in LANGUAGE_MARKERS.get(lang, set())}
                if any(m.lower() in marker_names for m in ws.markers):
                    break
                if not _has_language_files(ws, lang):
                    ws.languages.discard(lang)
                break

    workspaces.sort(key=lambda ws: str(ws.path))
    return workspaces


# ---------------- Install helpers (unchanged high-level behavior) ----------------
def _uv_pip_list_names() -> set[str]:
    names = set()
    if which("uv"):
        cp = run(["uv", "pip", "list"])
        if cp.returncode == 0:
            for ln in (cp.stdout or "").splitlines()[2:]:
                if parts := ln.split():
                    names.add(parts[0].lower())
            return names
    if pip := (shutil.which("pip3") or shutil.which("pip")):
        cp = run([pip, "list"])
        if cp.returncode == 0:
            for ln in (cp.stdout or "").splitlines()[2:]:
                if parts := ln.split():
                    names.add(parts[0].lower())
    return names


def _pkg_installed(name: str, installed: set[str]) -> bool:
    return name.lower() in installed


def _scan_python_imports(files: list[Path]) -> list[str]:
    imps = set()
    imp_re = re.compile(r"^\s*(?:from\s+([A-Za-z0-9_\.]+)\s+import|import\s+([A-Za-z0-9_\.]+))")
    for f in files:
        if f.suffix != ".py":
            continue
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not (m := imp_re.match(line)):
                    continue
                if mod := (m.group(1) or m.group(2) or "").split(".")[0]:
                    imps.add(mod.lower())
        except Exception:
            continue
    return sorted(imps)


def _install_python_packages(
    packages: list[str], description: str, cfg: OutputConfig
) -> subprocess.CompletedProcess[str]:
    """Install a list of python packages using the preferred pip/uv."""
    info(f"{description}: installing with preferred pip/uv", use_emoji=cfg.emoji)
    cp = _install_with_preferred_pip(packages)
    if cp.returncode != 0 and which("uv"):
        warn(
            f"{description}: uv pip install failed; trying 'uv run -m pip'",
            use_emoji=cfg.emoji,
        )
        cp = run(["uv", "run", "-m", "pip", "install", "-U"] + packages)
    if cp.returncode == 0:
        ok(f"{description} tools installed", use_emoji=cfg.emoji)
    else:
        fail(f"{description} install failed", use_emoji=cfg.emoji)
    return cp


def _install_python_toolchain(files: list[Path], cfg: OutputConfig) -> None:
    """Handle installation of Python tools, stubs, and plugins."""
    py_pkgs = sorted(
        list(
            {
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
                "pytest",
                "types-setuptools",
            }
        )
    )
    _install_python_packages(py_pkgs, "Python", cfg)
    installed = _uv_pip_list_names()
    stub_map = {
        "boto3": "boto3-stubs",
        "botocore": "botocore-stubs",
        "sqlalchemy": "sqlalchemy-stubs",
        "redis": "types-redis",
        "toml": "types-toml",
        "pymongo": "types-pymongo",
        "jinja2": "types-Jinja2",
        "click": "types-Click",
    }
    imports = set(_scan_python_imports(files))
    to_install_stubs: set[str] = set()
    for pkg, stub in stub_map.items():
        if _pkg_installed(pkg, installed) or (pkg in imports):
            to_install_stubs.add(stub)
    if to_install_stubs:
        if which("uv"):
            run(["uv", "add", "-q", "--dev"] + sorted(to_install_stubs))
        elif pip := shutil.which("pip3") or shutil.which("pip"):
            run([pip, "install", "-U"] + sorted(to_install_stubs))

    pylint_plugin_by_framework: Final[dict[str, str]] = {
        "django": "pylint-django",
        "flask": "pylint-flask",
        "celery": "pylint-celery",
        "pytest": "pylint-pytest",
        "sqlalchemy": "pylint-sqlalchemy",
        "odoo": "pylint-odoo",
        "quotes": "pylint-quotes",
    }
    want_plugins: set[str] = set()
    pylint_frameworks = set(pylint_plugin_by_framework.keys())
    for fw, plug in pylint_plugin_by_framework.items():
        if _pkg_installed(fw, installed) or (fw in imports and fw in pylint_frameworks):
            want_plugins.add(plug)

    if (ROOT / ".venv").is_dir():
        want_plugins.add("pylint-venv")

    if want_plugins:
        if which("uv"):
            run(["uv", "add", "-q", "--dev"] + sorted(want_plugins))
        elif pip := shutil.which("pip3") or shutil.which("pip"):
            run([pip, "install", "-U"] + sorted(want_plugins))


def perform_install(
    workspaces: list[Workspace],
    suites: list[LanguageSuite],
    files: list[Path],
    cfg: OutputConfig,
) -> None:
    section(
        "Installing toolchains (detected-only)",
        use_color=cfg.color,
    )
    enabled_set = {s.name for s in (suites or [])}
    py_ws = sorted({ws.path for ws in workspaces if "python" in ws.languages})
    js_ws = sorted({ws.path for ws in workspaces if "javascript" in ws.languages})
    go_ws = sorted({ws.path for ws in workspaces if "go" in ws.languages})
    rs_ws = sorted({ws.path for ws in workspaces if "rust" in ws.languages})
    md_ws = sorted({ws.path for ws in workspaces if "markdown" in ws.languages})
    if not any([py_ws, js_ws, go_ws, rs_ws, md_ws]):
        warn(
            "Nothing to install: no detected languages (JS requires package.json).",
            use_emoji=cfg.emoji,
        )
        return

    if py_ws and (not enabled_set or "python" in enabled_set):
        info(
            f"Python detected in {len(py_ws)} workspace(s); installing Python tools once.",
            use_emoji=cfg.emoji,
        )
        _install_python_toolchain(files, cfg)

    if md_ws and (not enabled_set or "markdown" in enabled_set):
        info(
            f"Markdown detected in {len(md_ws)} workspace(s); installing Markdown tools once.",
            use_emoji=cfg.emoji,
        )
        md_pkgs = sorted(
            list(
                {
                    "mdformat",
                    "mdformat-gfm",
                    "mdformat-frontmatter",
                    "mdformat-footnote",
                    "mdformat-gfm-alerts",
                    "mdformat-myst",
                }
            )
        )
        _install_python_packages(md_pkgs, "Markdown", cfg)

    if js_ws and (not enabled_set or "javascript" in enabled_set):
        _install_javascript_toolchain(js_ws, cfg)
    if go_ws and (not enabled_set or "go" in enabled_set):
        if which("go"):
            for ws in go_ws:
                if (ws / "go.mod").is_file():
                    info(f"Go: running go mod tidy in {ws}", use_emoji=cfg.emoji)
                    run(["go", "mod", "tidy"], cwd=ws)
            info("Go: installing golangci-lint (once)", use_emoji=cfg.emoji)
            run(
                [
                    "go",
                    "install",
                    "github.com/golangci/golangci-lint/cmd/golangci-lint@latest",
                ]
            )
            ok("Go setup attempted", use_emoji=cfg.emoji)
        else:
            warn("Go: 'go' not found; skipping", use_emoji=cfg.emoji)

    if rs_ws and (not enabled_set or "rust" in enabled_set):
        if which("rustup"):
            info("Rust: ensuring rustfmt & clippy via rustup", use_emoji=cfg.emoji)
            run(["rustup", "component", "add", "rustfmt"])
            run(["rustup", "component", "add", "clippy"])
            ok("Rust components ensured", use_emoji=cfg.emoji)
        else:
            warn(
                "Rust: rustup not found; skipping component install",
                use_emoji=cfg.emoji,
            )


def _install_javascript_toolchain(js_workspaces: list[Path], cfg: OutputConfig) -> None:
    """Handle installation of JavaScript tools in each relevant workspace."""
    if not which("npm"):
        warn("JavaScript: npm not found; skipping JS tool installs", use_emoji=cfg.emoji)
        return

    devs = ["eslint", "prettier", "typescript", "jest", "@types/node"]
    for ws in js_workspaces:
        info(f"JavaScript: installing dev tools in {ws}", use_emoji=cfg.emoji)
        if (ws / "package-lock.json").is_file():
            run(
                ["npm", "ci", "--no-audit", "--fund=false"],
                cwd=ws,
                env=NODE_ENV_DEFAULTS,
            )
        cp = run(
            ["npm", "install", "--no-audit", "--fund=false", "-D"] + devs,
            cwd=ws,
            env=NODE_ENV_DEFAULTS,
        )
        if cp.returncode == 0:
            ok(f"JS tools installed in {ws}", use_emoji=cfg.emoji)
        else:
            warn(f"npm install dev tools failed in {ws}", use_emoji=cfg.emoji)


# ---------------- Runner ----------------
def discover_suites(cfg: ExecutionConfig, workspaces: list[Workspace]) -> list[LanguageSuite]:
    selected: list[LanguageSuite] = []
    requested = {name.lower() for name in cfg.languages}
    enabled = {name.lower() for name in cfg.enable}
    available: set[str] = set()
    for ws in workspaces:
        available.update(lang.lower() for lang in ws.languages)

    for suite in SUITES:
        name = suite.name.lower()
        if requested:
            if name in requested or name in enabled:
                selected.append(suite)
            continue
        if name in enabled or name in available:
            selected.append(suite)
            continue
        if suite.detector(ROOT):
            selected.append(suite)
    return selected


def _get_cached_step(tool: Tool, cmd: list[str], footprint: list[Path], ctx: ToolRunContext) -> CachePayload | None:
    if not ctx.exec_cfg.cache_enabled:
        return None
    _prune_cache(ctx.exec_cfg.cache_dir)
    ver = _tool_version(cmd)
    conf_hash = _hash_configs(_config_files_for_tool(tool.name, ROOT))
    key_args = CacheKeyArgs(cmd=cmd, files=footprint, version=ver, config_hash=conf_hash)
    key = _cache_key(key_args)
    load_args = CacheLoadArgs(cache_dir=ctx.exec_cfg.cache_dir, key=key, files=footprint)
    cached_step: CachePayload | None = _cache_load(load_args)
    if cached_step and ctx.output_cfg.verbose:
        info(f"cache hit: {key[:8]} for {tool.name}", use_emoji=ctx.output_cfg.emoji)
    return cached_step


def _save_step_to_cache(
    tool: Tool,
    cmd: list[str],
    footprint: list[Path],
    payload: CachePayload,
    ctx: ToolRunContext,
) -> None:
    if not ctx.exec_cfg.cache_enabled:
        return
    try:
        ver = _tool_version(cmd)
        conf_hash = _hash_configs(_config_files_for_tool(tool.name, ROOT))
        key_args = CacheKeyArgs(cmd=cmd, files=footprint, version=ver, config_hash=conf_hash)
        key = _cache_key(key_args)
        save_args = CacheSaveArgs(cache_dir=ctx.exec_cfg.cache_dir, key=key, files=footprint, payload=payload)
        _cache_save(save_args)
    except Exception:
        pass  # Never crash on cache-related errors


def _parse_tool_output(
    tool: Tool,
    cmd: list[str],
    output_text: str,
    use_json_diags: bool,
    _ctx: ToolRunContext,
) -> list[Diagnostic]:
    if not tool.parser:
        return []

    text_parser = getattr(tool.parser, "text_parser", None)
    json_parser = getattr(tool.parser, "json_parser", None)
    ann_fmt = ANNOTATION_FORMATS.get(tool.name)

    if use_json_diags and json_parser and ann_fmt:
        ann_cmd = ann_fmt.augment(cmd)
        ann_cp = run(ann_cmd)
        if payload := _json_loads_forgiving((ann_cp.stdout or "").strip()):
            parsed_diags: list[Diagnostic] = json_parser.parse(payload)
            return parsed_diags

    if text_parser:
        return text_parser.parse(output_text)
    return []


def run_tool(args: RunToolArgs) -> ToolOutcome:
    tool, ctx = args.tool, args.ctx
    outcome = ToolOutcome(suite=ctx.suite_name, tool=tool.name, failed=False, steps=[])
    if not tool.actions:
        return outcome
    if not tool.is_available():
        fail(
            f"{tool.name}: skipped (missing executable '{tool.actions[0].cmd.base_cmd[0]}')",
            use_emoji=ctx.output_cfg.emoji,
        )
        outcome.steps.append(
            ToolOutcomeStep(
                action="__init__",
                rc=0,
                stdout="",
                stderr="",
                raw_stdout="",
                raw_stderr="",
                diagnostics=[],
                skipped=True,
                skip_reason="missing executable",
            )
        )
        if ctx.exec_cfg.strict:
            outcome.failed = True
        return outcome

    # Filter actions by global fix-only / check-only
    actions = list(tool.actions)
    if ctx.exec_cfg.fix_only:
        actions = [a for a in actions if a.is_fix]
    if ctx.exec_cfg.check_only:
        actions = [a for a in actions if not a.is_fix]
    if not actions:
        return outcome

    relevant = tool.select_files(ctx.files)
    if tool.file_extensions and not relevant:
        warn(f"{tool.name}: skipped (no relevant files)", use_emoji=ctx.output_cfg.emoji)
        outcome.steps.append(
            ToolOutcomeStep(
                action="__init__",
                rc=0,
                stdout="",
                stderr="",
                raw_stdout="",
                raw_stderr="",
                diagnostics=[],
                skipped=True,
                skip_reason="no relevant files",
            )
        )
        return outcome

    failed = False
    for action in actions:
        files_to_pass = relevant if relevant else ([ctx.workspace_path] if tool.run_on_project_if_no_files else [])
        cmd_args = BuildCmdArgs(action=action, files=files_to_pass, cfg=ctx.cfg, root=ctx.workspace_path)
        cmd = tool.runner.build_cmd(cmd_args)
        normalized_cmd, inferred_env = _normalize_command(cmd, files_to_pass or ctx.files)
        cmd = normalized_cmd
        env_for_cmd: dict[str, str] | None = None
        if inferred_env:
            env_for_cmd = dict(inferred_env)
        if action.env:
            env_for_cmd = env_for_cmd or {}
            env_for_cmd.update(action.env)
        if ctx.output_cfg.verbose:
            info(
                f"▶ {ctx.suite_name}:{tool.name}:{action.name} {shlex.join(cmd)}",
                use_emoji=ctx.output_cfg.emoji,
            )
        footprint = relevant if relevant else ctx.files
        cached_step = _get_cached_step(tool, cmd, footprint, ctx)
        diags: list[Diagnostic] = []
        if cached_step:
            cp = subprocess.CompletedProcess(cmd, cached_step.rc, cached_step.raw_stdout, cached_step.raw_stderr)
            diags = cached_step.diagnostics
        else:
            cp = run(cmd, env=env_for_cmd, timeout=action.timeout_s)
            output_text = (cp.stdout or "") + "\n" + (cp.stderr or "")
            use_json = ctx.output_cfg.annotations_use_json or tool.force_json_for_diags
            diags = _parse_tool_output(tool, cmd, output_text, use_json, ctx)

        out = action.out_filter.apply(cp.stdout)
        err = action.out_filter.apply(cp.stderr)
        rc = cp.returncode
        if (
            rc == 0
            and action.failure_on_output_regex
            and re.search(action.failure_on_output_regex, cp.stdout + cp.stderr, re.MULTILINE)
        ):
            rc = 1
        if rc != 0 and not action.ignore_exit:
            failed = True

        if rc != 0:
            fail(
                f"{ctx.suite_name}:{tool.name}:{action.name}",
                use_emoji=ctx.output_cfg.emoji,
            )
            if ctx.output_cfg.output == "raw":
                print(out or err or "(no output)", file=sys.stderr if err else sys.stdout)
        else:
            ok(
                f"{ctx.suite_name}:{tool.name}:{action.name}",
                use_emoji=ctx.output_cfg.emoji,
            )
            if ctx.output_cfg.show_passing and ctx.output_cfg.output == "raw" and (out or err):
                print(out or err, file=sys.stderr if err else sys.stdout)

        if cached_step is None:
            payload = CachePayload(
                rc=rc,
                stdout=out,
                stderr=err,
                raw_stdout=cp.stdout or "",
                raw_stderr=cp.stderr or "",
                diagnostics=diags,
                ts=time.time(),
            )
            _save_step_to_cache(tool, cmd, footprint, payload, ctx)

        if ctx.output_cfg.gha_annotations and rc != 0 and not ctx.cfg.dedupe.dedupe:
            if diags:
                for d in diags:
                    _gha_emit(
                        GhaAnnotation(
                            kind=_sarif_level(d.severity),
                            file=d.file,
                            line=d.line,
                            col=d.col,
                            title=d.title or tool.name,
                            message=d.message or "",
                        )
                    )
            else:
                output_text_for_gha = (cp.stdout or "") + "\n" + (cp.stderr or "")
                emit_gha_annotations(tool, output_text_for_gha)

        outcome.steps.append(
            ToolOutcomeStep(
                action=action.name,
                rc=rc,
                stdout=out,
                stderr=err,
                raw_stdout=cp.stdout or "",
                raw_stderr=cp.stderr or "",
                diagnostics=diags,
                skipped=False,
                cached=(cached_step is not None),
            )
        )
    outcome.failed = failed
    return outcome


def _run_tools_parallel(suite: LanguageSuite, tools: list[Tool], ctx: ToolRunContext) -> list[ToolOutcome]:
    results = []
    crashed_tools: list[ToolException] = []
    max_workers = max(1, int(ctx.exec_cfg.jobs or (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {}
        for tool in tools:
            if ctx.exec_cfg.only and tool.name.lower() not in ctx.exec_cfg.only:
                continue
            fut = ex.submit(run_tool, RunToolArgs(tool=tool, ctx=ctx))
            futs[fut] = tool.name
        for fut in as_completed(futs):
            tool_name = futs[fut]
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                crashed_tools.append(ToolException(tool_name, e))
                outcome = ToolOutcome(
                    suite=suite.name,
                    tool=tool_name,
                    failed=True,
                    crashed=True,
                    crash_reason=str(e),
                )
                results.append(outcome)

    if crashed_tools:
        # If all tools in the suite crashed with the same error, show one critical message.
        first_error_msg = str(crashed_tools[0].original_exc)
        if len(crashed_tools) == len(
            [t for t in tools if not ctx.exec_cfg.only or t.name.lower() in ctx.exec_cfg.only]
        ) and all(str(e.original_exc) == first_error_msg for e in crashed_tools):
            fail(
                f"CRITICAL: All tools in suite '{suite.name}' crashed with the same error:\n  {first_error_msg}",
                use_emoji=ctx.output_cfg.emoji,
            )
        else:
            # Otherwise, report individual crashes.
            for exc in crashed_tools:
                warn(
                    f"{suite.name}:{exc.tool_name} crashed: {exc.original_exc}",
                    use_emoji=ctx.output_cfg.emoji,
                )

    return results


# ---------------- Waivers & Hints ----------------
def waiver_inventory(files: list[Path]) -> dict[str, int]:
    rx = {
        "noqa": re.compile(r"#\s*noqa(\b|:)", re.I),
        "pylint_disable": re.compile(r"pylint:\s*disable", re.I),
        "eslint_disable_next": re.compile(r"//\s*eslint-disable-next-line\b"),
        "eslint_disable": re.compile(r"/\*\s*eslint-disable", re.I),
        "ts_ignore": re.compile(r"//\s*@ts-ignore\b"),
        "ts_expect_error": re.compile(r"//\s*@ts-expect-error\b"),
    }
    counts = {k: 0 for k in rx}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for k, pat in rx.items():
            counts[k] += len(pat.findall(text))
    return counts


QUICK_FIX_HINTS: Final[dict[str, str]] = {
    "import": "Check installed packages and import paths; try: ruff --fix, isort, or add missing dependency.",
    "undefined": "Define the symbol or import it; for TS, add types; for Python, check names and __init__.py exports.",
    "unused-import": "Remove the import or use it; ruff/isort can auto-fix.",
    "unused-variable": "Delete unused vars or prefix with _ to signal intent.",
    "formatting": "Run formatters (black/prettier/gofmt/rustfmt).",
    "type": "Adjust annotations/types; for mypy/tsc, follow the error’s suggested type.",
    "syntax": "Fix syntax; sometimes a missing comma/paren.",
    "security": "Review the finding; avoid unsafe APIs; sanitize inputs.",
    "deadcode": "Delete unreachable/unused code (vulture can help).",
    "complexity": "Refactor into smaller functions or reduce branches.",
    "performance": "Consider algorithmic improvements or vectorization.",
}


def emit_hints(outcomes: list[ToolOutcome], cfg: OutputConfig) -> None:
    present = set()
    for o in outcomes:
        for s in o.steps:
            for d in s.diagnostics or []:
                g = d.group or _classify_issue(d.title, d.code, d.message)
                if g:
                    present.add(g)
    if tips := [f"- **{g}**: {QUICK_FIX_HINTS[g]}" for g in sorted(QUICK_FIX_HINTS) if g in present]:
        section("Quick Fix Hints", use_color=cfg.color)
        for t in tips[:10]:
            print(t)


def write_pr_summary(outcomes: list[ToolOutcome], path: Path, limit: int = 100) -> None:
    items: list[Diagnostic] = []
    for o in outcomes:
        for s in o.steps:
            items += s.diagnostics or []
    if not items:
        path.write_text("**No findings 🎉**\n", encoding="utf-8")
        return
    by_group: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for d in items:
        if g := d.group or _classify_issue(d.title, d.code, d.message):
            by_group[g] = by_group.get(g, 0) + 1
        f = _relpath(d.file or "")
        by_file[f] = by_file.get(f, 0) + 1
    lines = []
    lines.append("### Lint Summary (deduped)")
    lines.append(f"- **Total**: {len(items)}")
    lines.append(
        "- **Top groups**: " + ", ".join(f"{g}:{n}" for g, n in sorted(by_group.items(), key=lambda x: -x[1])[:8])
    )
    lines.append(
        "- **Top files**: " + ", ".join(f"{f}:{n}" for f, n in sorted(by_file.items(), key=lambda x: -x[1])[:8])
    )
    lines.append("")
    lines.append("| Severity | Group | File | Line | Col | Tool | Code | Message |")
    lines.append("|---|---|---|---:|---:|---|---|---|")
    for d in items[:limit]:
        lines.append(
            f"| {d.severity.value.upper()} | {d.group or _classify_issue(d.title, d.code, d.message)} | {_relpath(d.file or '')} | {d.line or 1} | {d.col or 1} | {d.title or ''} | {d.code or ''} | {(d.message or '').replace('|', r'\\|')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------- CLI / Main ----------------
EXECUTABLE_MODE = 0o755


def _get_changed_files(cfg: FileDiscoveryConfig, all_files: list[Path], emoji: bool) -> list[Path]:
    if cfg.pre_commit:
        changed = set(git_staged_paths())
        if not changed:
            warn("No staged files detected; skipping file-scoped tools.", use_emoji=emoji)
        info(f"Staged files: {len(changed)}", use_emoji=emoji)
        return [p for p in all_files if p in changed]

    changed = set(git_changed_paths(cfg.diff_ref, cfg.include_untracked))
    if not changed:
        warn("No changed files detected; skipping file-scoped tools.", use_emoji=emoji)
    info(f"Changed files vs {cfg.diff_ref}: {len(changed)}", use_emoji=emoji)
    return [p for p in all_files if p in changed]


def _setup_and_discover_files(cfg: FileDiscoveryConfig) -> list[Path]:
    section("Discovering files", use_color=True)  # Color/emoji not available here yet
    all_files = list_repo_files(
        cfg.roots,
        excludes=cfg.excludes,
        prefer_git=True,
        respect_gitignore=cfg.respect_gitignore,
    )

    if cfg.paths_from_stdin:
        if stdin_paths := {Path(line.strip()) for line in sys.stdin if line.strip()}:
            all_files = [p for p in all_files if p in stdin_paths]
        info(f"Paths from stdin: {len(all_files)}", use_emoji=True)

    if cfg.base_branch:
        if base := git_merge_base(cfg.base_branch):
            cfg.diff_ref = base
            cfg.changed_only = True
            info(
                f"Using merge-base with {cfg.base_branch}: {cfg.diff_ref}",
                use_emoji=True,
            )
        else:
            warn(
                f"Could not compute merge-base with {cfg.base_branch}; falling back to {cfg.diff_ref}.",
                use_emoji=True,
            )

    if not (cfg.pre_commit or cfg.changed_only):
        info(f"Found {len(all_files)} files after exclusions.", use_emoji=True)
        return all_files
    return _get_changed_files(cfg, all_files, emoji=True)


def _run_suite_tools(
    suite: LanguageSuite,
    workspace: Workspace,
    ctx: LintingContext,
) -> list[ToolOutcome]:
    """Prepares and runs all tools for a given suite in the current workspace context."""
    section(f"Running {suite.name} tools", use_color=ctx.output_cfg.color)
    tools = suite.tools_factory(ROOT)
    if suite.name == "python" and not detect_smoke_enabled():
        tools = [t for t in tools if t.name != "pytest"]
        fail("pytest: skipped (no smoke tests found)", use_emoji=ctx.output_cfg.emoji)
    else:
        # propagate excludes to ruff/mypy
        exclude_flags: list[str] = []
        for pth in ctx.file_cfg.excludes:
            candidate = Path(pth)
            try:
                rel = candidate.resolve().relative_to(workspace.path.resolve())
                target = str(rel)
            except Exception:
                target = str(candidate)
            exclude_flags.extend(["--exclude", target])
        for t in tools:
            if t.name in {"ruff", "mypy"}:
                for a in t.actions:
                    if a.cmd.base_cmd[:2] == ["ruff", "check"]:
                        a.cmd.base_cmd = a.cmd.base_cmd[:2] + exclude_flags + a.cmd.base_cmd[2:]
                    if a.cmd.base_cmd and a.cmd.base_cmd[0] == "mypy":
                        a.cmd.base_cmd = a.cmd.base_cmd + exclude_flags

    files_for_ctx = workspace.files if workspace.files else ctx.all_files
    run_ctx = ToolRunContext(
        suite_name=suite.name,
        files=files_for_ctx,
        workspace_path=workspace.path,
        exec_cfg=ctx.exec_cfg,
        output_cfg=ctx.output_cfg,
        cfg=ctx.cfg,
    )
    return _run_tools_parallel(suite, tools, run_ctx)


def _run_linters_in_workspaces(ctx: LintingContext) -> list[ToolOutcome]:
    all_outcomes: list[ToolOutcome] = []
    orig_root = ROOT

    for workspace in ctx.workspaces:
        ws_path = workspace.path
        lang_display = ", ".join(sorted(workspace.languages)) or "default"
        section(
            f"Workspace: {workspace.display_name()} [{lang_display}]",
            use_color=ctx.output_cfg.color,
        )
        globals()["ROOT"] = ws_path

        if (
            not ctx.exec_cfg.force_all
            and ws_path == ROOT
            and not workspace.files
            and not workspace.languages
            and len(ctx.workspaces) > 1
        ):
            continue

        suites_ws = ctx.suites
        if not ctx.exec_cfg.force_all:
            if workspace.languages:
                suites_ws = [s for s in ctx.suites if s.name in workspace.languages]
            elif ws_path != ROOT:
                suites_ws = []
        if not suites_ws:
            continue

        if ctx.file_cfg.changed_only or ctx.file_cfg.pre_commit:
            heuristic_files = workspace.files
        else:
            heuristic_files = workspace.files if workspace.files else ctx.all_files
        suites_ws = apply_skip_heuristics(suites_ws, heuristic_files, ctx.exec_cfg)

        # Per-workspace cache dir
        ws_hash = hashlib.sha256(str(ws_path.resolve()).encode(), usedforsecurity=False).hexdigest()[:8]
        exec_cfg_ws = ctx.exec_cfg
        exec_cfg_ws.cache_dir = Path(".lint-cache") / ws_hash

        for suite in suites_ws:
            all_outcomes.extend(_run_suite_tools(suite, workspace, ctx))

    globals()["ROOT"] = orig_root
    return all_outcomes


def _process_results_and_artifacts(ctx: ProcessingContext) -> int:
    wants_compact = ctx.output_cfg.output in {"pretty", "concise"}
    if wants_compact and not ctx.dedupe_cfg.dedupe:
        ctx.dedupe_cfg.dedupe = True

    concise_snapshot: list[Diagnostic] | None = None
    if ctx.output_cfg.output == "pretty":
        processed_outcomes = dedupe_outcomes(ctx.outcomes, ctx.dedupe_cfg) if ctx.dedupe_cfg.dedupe else ctx.outcomes
        emit_pretty(processed_outcomes, ctx.output_cfg)
        emit_hints(processed_outcomes, ctx.output_cfg)
    elif ctx.output_cfg.output == "concise":
        processed_outcomes = dedupe_outcomes(ctx.outcomes, ctx.dedupe_cfg) if ctx.dedupe_cfg.dedupe else ctx.outcomes
        concise_snapshot = print_concise(processed_outcomes, ctx.output_cfg)
    else:
        processed_outcomes = ctx.outcomes

    if ctx.output_cfg.output != "concise":
        section("Summary", use_color=ctx.output_cfg.color)
    inv = waiver_inventory(ctx.files)

    all_diags = concise_snapshot or _deduped_items(processed_outcomes)
    error_count = sum(1 for d in all_diags if d.severity == Severity.ERROR)
    warning_count = sum(1 for d in all_diags if d.severity == Severity.WARNING)
    notice_count = sum(1 for d in all_diags if d.severity in {Severity.NOTICE, Severity.NOTE})

    go_message: str | None = None
    if ctx.output_cfg.output == "concise":
        summary_line = (
            f"Summary: files={len(ctx.files)} diagnostics={len(all_diags)} "
            f"errors={error_count} warnings={warning_count} notices={notice_count} "
            f"waivers=noqa:{inv['noqa']},pylint-disable:{inv['pylint_disable']}"
        )
        print(summary_line)
        go = error_count == 0 and warning_count == 0
        if go:
            go_message = "GO — lint checks are clean"
        else:
            detail_parts: list[str] = []
            if error_count:
                detail_parts.append(f"{error_count} error(s)")
            if warning_count:
                detail_parts.append(f"{warning_count} warning(s)")
            go_message = f"NO GO — fix {' and '.join(detail_parts)}"
    else:
        info(
            f"Waivers → noqa:{inv['noqa']} | pylint:disable:{inv['pylint_disable']} | "
            f"eslint-disable-next-line:{inv['eslint_disable_next']} | eslint-disable:{inv['eslint_disable']} | "
            f"@ts-ignore:{inv['ts_ignore']} | @ts-expect-error:{inv['ts_expect_error']}",
            use_emoji=ctx.output_cfg.emoji,
        )

        by_group: dict[str, int] = {}
        for d in all_diags:
            if d.group:
                by_group[d.group] = by_group.get(d.group, 0) + 1

        total_loc = _count_loc(ctx.files)
        errors_per_kloc = (error_count / total_loc * 1000) if total_loc > 0 else 0

        group_stats = ", ".join(f"{k}:{v}" for k, v in sorted(by_group.items()))
        metrics_line = f"Metrics → Errors: {error_count} | By group: {group_stats} | Errors/kLOC: {errors_per_kloc:.2f}"
        info(metrics_line, use_emoji=ctx.output_cfg.emoji)

    if ctx.dedupe_cfg.dedupe and ctx.output_cfg.output not in {"pretty", "concise"}:
        processed_outcomes = dedupe_outcomes(ctx.outcomes, ctx.dedupe_cfg)
        ok("Deduped diagnostics across tools", use_emoji=ctx.output_cfg.emoji)

    if ctx.output_cfg.gha_annotations and ctx.dedupe_cfg.dedupe:
        for o in processed_outcomes:
            for s in o.steps:
                for d in s.diagnostics or []:
                    kind: Literal["error", "warning", "notice"] = (
                        "notice"
                        if d.severity in {Severity.NOTICE, Severity.NOTE}
                        else ("warning" if d.severity == Severity.WARNING else "error")
                    )
                    _gha_emit(
                        GhaAnnotation(
                            kind=kind,
                            file=d.file,
                            line=d.line,
                            col=d.col,
                            title=d.title or o.tool,
                            message=d.message or "",
                        )
                    )

    if ctx.output_cfg.report == "json":
        report_obj = outcomes_to_report(
            processed_outcomes,
            files_scanned=len(ctx.files),
            include_raw=ctx.output_cfg.report_include_raw,
        )
        out_text = json.dumps(report_obj, indent=2)
        if ctx.output_cfg.report_out:
            ctx.output_cfg.report_out.write_text(out_text, encoding="utf-8")
            ok(
                f"Wrote JSON report to {ctx.output_cfg.report_out}",
                use_emoji=ctx.output_cfg.emoji,
            )
        else:
            print(out_text)

    if ctx.output_cfg.sarif_out:
        sarif_obj = build_sarif(processed_outcomes)
        ctx.output_cfg.sarif_out.write_text(json.dumps(sarif_obj, indent=2), encoding="utf-8")
        ok(f"Wrote SARIF to {ctx.output_cfg.sarif_out}", use_emoji=ctx.output_cfg.emoji)
    if ctx.output_cfg.pr_summary_out:
        write_pr_summary(
            processed_outcomes,
            ctx.output_cfg.pr_summary_out,
            ctx.output_cfg.pr_summary_limit,
        )
        ok(
            f"Wrote PR summary to {ctx.output_cfg.pr_summary_out}",
            use_emoji=ctx.output_cfg.emoji,
        )

    failed = [o for o in processed_outcomes if o.failed]
    skipped_missing = any(
        any(s.skipped and s.skip_reason == "missing executable" for s in o.steps) for o in processed_outcomes
    )

    if failed:
        for o in failed:
            fail(f"{o.suite}:{o.tool} failed", use_emoji=ctx.output_cfg.emoji)
        fail(
            "FAILED running linters. Treat all warnings as errors.",
            use_emoji=ctx.output_cfg.emoji,
        )
        if go_message:
            print(go_message)
        return 1

    if ctx.exec_cfg.strict and skipped_missing:
        fail(
            "STRICT mode: missing required tools detected.",
            use_emoji=ctx.output_cfg.emoji,
        )
        if go_message:
            print(go_message)
        return 1

    ok("All lint checks passed!", use_emoji=ctx.output_cfg.emoji)
    if go_message:
        print(go_message)
    return 0


def _parse_args_and_build_config(
    argv: list[str] | None,
) -> tuple[argparse.Namespace, Config]:
    parser = argparse.ArgumentParser(
        prog="lint.py",
        description="Stdlib-only multi-language linter runner with parallel orchestration, smart caching, monorepo awareness, security suite, skip heuristics, fix→check sequencing, JSON+SARIF+PR artifacts, GH annotations, pretty stdout, dedupe, uv/.venv runners, and installer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # --- Add all arguments (this part remains the same) ---
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to lint.")
    # Output & Display
    parser.add_argument("--no-emoji", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--show-passing", action="store_true")
    parser.add_argument(
        "--output",
        choices=["pretty", "raw", "concise"],
        default="concise",
        help="Pretty (grouped) stdout, raw per-tool logs, or concise agent-friendly summary.",
    )
    parser.add_argument(
        "--pretty-format",
        choices=["text", "jsonl", "markdown"],
        default="text",
        help="Pretty output format.",
    )
    parser.add_argument(
        "--group-by-code",
        action="store_true",
        help="Group pretty text output by tool/code instead of by file.",
    )
    parser.add_argument(
        "--gitignore",
        action="store_true",
        help="Respect .gitignore entries during file discovery.",
    )
    # File Discovery
    parser.add_argument("--exclude", action="append", default=[], help="Path to exclude. Repeatable.")
    parser.add_argument(
        "--paths-from-stdin",
        action="store_true",
        help="Read newline-delimited paths from stdin to scope linting.",
    )
    # Git-related Discovery
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Lint only files changed vs --diff-ref (and untracked by default).",
    )
    parser.add_argument("--diff-ref", default="HEAD", help="Git ref for --changed-only.")
    parser.add_argument(
        "--no-include-untracked",
        action="store_true",
        help="Omit untracked files in --changed-only.",
    )
    parser.add_argument(
        "--base-branch",
        default=None,
        help="Compute merge-base with this branch and use as --diff-ref (implies --changed-only).",
    )
    parser.add_argument("--pre-commit", action="store_true", help="Run on staged files only.")
    # Execution Control
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only these tool names (repeatable).",
    )
    parser.add_argument(
        "--lang",
        action="append",
        default=[],
        help="Limit to suites by name (python, javascript, go, rust, security).",
    )
    parser.add_argument(
        "--enable",
        action="append",
        default=[],
        help="Enable optional suites (e.g., security). Repeatable.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any tool is skipped due to missing executable.",
    )
    parser.add_argument("--jobs", type=int, default=None, help="Max parallel tools (default: CPUs).")
    parser.add_argument("--fix-only", action="store_true", help="Run only fixers across all tools.")
    parser.add_argument("--check-only", action="store_true", help="Run only checkers across all tools.")
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Disable skip heuristics; run all suites.",
    )
    parser.add_argument(
        "--respect-config",
        action="store_true",
        help="Defer to project configs when present (pyproject, mypy.ini, .eslintrc*, prettier, tsconfig).",
    )
    # Caching
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable on-disk caching in .lint-cache (1h TTL).",
    )
    # Reporting & Artifacts
    parser.add_argument("--report", choices=["json"], default=None, help="Emit machine-readable report.")
    parser.add_argument(
        "--report-out",
        default=None,
        help="Write report to this file (stdout if omitted).",
    )
    parser.add_argument(
        "--report-include-raw",
        action="store_true",
        help="Include raw stdout/stderr in report steps.",
    )
    parser.add_argument(
        "--sarif-out",
        default=None,
        help="Write Code Scanning SARIF (2.1.0) to this path.",
    )
    parser.add_argument(
        "--pr-summary-out",
        default=None,
        help="Write a short PR-ready Markdown summary here.",
    )
    parser.add_argument("--pr-summary-limit", type=int, default=100, help="Max issues in PR summary.")
    # GHA Integration
    parser.add_argument(
        "--gha-annotations",
        action="store_true",
        help="Emit ::error/::warning/::notice lines for failing steps.",
    )
    parser.add_argument(
        "--annotations-use-json",
        action="store_true",
        help="Use structured (JSON) outputs for annotations when supported.",
    )
    # Deduplication
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Dedupe diagnostics across tools (keep only one per issue).",
    )
    parser.add_argument(
        "--dedupe-by",
        choices=["first", "severity", "prefer"],
        default="first",
        help="When deduping, which report to keep.",
    )
    parser.add_argument(
        "--dedupe-prefer",
        default="ruff,pyright,mypy,pylint,eslint,golangci-lint,clippy,cargo-test,bandit",
        help="Comma-separated tool precedence when --dedupe-by=prefer.",
    )
    parser.add_argument(
        "--dedupe-line-fuzz",
        type=int,
        default=2,
        help="Treat diagnostics within this many lines as the same issue.",
    )
    parser.add_argument(
        "--no-dedupe-same-file-only",
        dest="dedupe_same_file_only",
        action="store_false",
        help="Allow dedupe across files (rare).",
    )
    # Misc/Meta
    parser.add_argument(
        "--severity-rule",
        action="append",
        default=[],
        help="Custom severity mapping: TOOL:REGEX=level (level=error|warning|notice). Repeatable.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install toolchains (install-only; does not run linters).",
    )
    parser.add_argument(
        "--install-and-run",
        action="store_true",
        help="Install toolchains, then run linters in the same invocation.",
    )
    parser.add_argument(
        "--install-pre-commit-hook",
        action="store_true",
        help="Install a .git/hooks/pre-commit that runs this with --pre-commit.",
    )

    args = parser.parse_args(argv)

    if args.install and not args.lang:
        parser.error("--install now requires at least one --lang suite to target.")

    # --- Build the composed Config object from args ---
    exclude_paths: set[Path] = {Path("pyreadstat_patch")}
    exclude_paths.update(Path(p) for p in args.exclude)
    exclude_paths.update(Path(name) for name in ALWAYS_EXCLUDE_DIRS)

    file_discovery_cfg = FileDiscoveryConfig(
        roots=[Path(p) for p in (args.paths or ["."])],
        excludes=sorted(exclude_paths),
        paths_from_stdin=args.paths_from_stdin,
        changed_only=args.changed_only,
        diff_ref=args.diff_ref,
        include_untracked=not args.no_include_untracked,
        base_branch=args.base_branch,
        pre_commit=args.pre_commit,
        respect_gitignore=args.gitignore,
    )

    output_cfg = OutputConfig(
        verbose=args.verbose,
        emoji=not args.no_emoji,
        color=not args.no_color,
        show_passing=args.show_passing,
        output=args.output,
        pretty_format=args.pretty_format,
        group_by_code=args.group_by_code,
        report=args.report,
        report_out=Path(args.report_out) if args.report_out else None,
        report_include_raw=args.report_include_raw,
        sarif_out=Path(args.sarif_out) if args.sarif_out else None,
        pr_summary_out=Path(args.pr_summary_out) if args.pr_summary_out else None,
        pr_summary_limit=args.pr_summary_limit,
        gha_annotations=args.gha_annotations,
        annotations_use_json=args.annotations_use_json,
    )

    execution_cfg = ExecutionConfig(
        only=[o.lower() for o in args.only],
        languages=[lang_name.lower() for lang_name in args.lang],
        enable=[e.lower() for e in args.enable],
        strict=args.strict,
        jobs=(args.jobs or (os.cpu_count() or 4)),
        fix_only=args.fix_only,
        check_only=args.check_only,
        force_all=args.force_all,
        respect_config=args.respect_config,
        cache_enabled=not args.no_cache,
    )

    dedupe_cfg = DedupeConfig(
        dedupe=args.dedupe,
        dedupe_by=args.dedupe_by,
        dedupe_prefer=[t.strip() for t in (args.dedupe_prefer or "").split(",") if t.strip()],
        dedupe_line_fuzz=args.dedupe_line_fuzz,
        dedupe_same_file_only=args.dedupe_same_file_only,
    )

    cfg = Config(
        file_discovery=file_discovery_cfg,
        output=output_cfg,
        execution=execution_cfg,
        dedupe=dedupe_cfg,
        severity_rules=args.severity_rule,
    )

    return args, cfg


def main(argv: list[str] | None = None) -> int:
    args, cfg = _parse_args_and_build_config(argv)

    for spec in cfg.severity_rules:
        if e := add_custom_rule(spec):
            warn(e, use_emoji=cfg.output.emoji)

    if args.install_pre_commit_hook:
        if not which("git"):
            fail(
                "Cannot install pre-commit hook: git not found.",
                use_emoji=cfg.output.emoji,
            )
            return 1
        hook_dir = Path(".git/hooks")
        hook_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hook_dir / "pre-commit"
        this_script = Path(__file__).resolve()
        hook_path.write_text(
            f"#!/usr/bin/env bash\npython3 \"{this_script}\" --pre-commit\nret=$?\n[ $ret -ne 0 ] && echo 'lint.py pre-commit hook failed.'\nexit $ret\n",
            encoding="utf-8",
        )
        os.chmod(hook_path, EXECUTABLE_MODE)
        ok(f"Installed pre-commit hook at {hook_path}", use_emoji=cfg.output.emoji)
        return 0

    all_files = _setup_and_discover_files(cfg.file_discovery)

    workspaces = discover_workspaces(ROOT, all_files)

    section("Detecting language suites", use_color=cfg.output.color)
    suites = discover_suites(cfg.execution, workspaces)
    if args.install or args.install_and_run:
        r = perform_install_entrypoint(
            workspaces,
            suites,
            all_files,
            cfg.output,
            install_and_run=args.install_and_run,
        )
        if r is not None:
            return r

    if not suites:
        warn("No language suites detected — nothing to do.", use_emoji=cfg.output.emoji)
        return 0
    for s in suites:
        ok(f"Enabled suite: {s.name}", use_emoji=cfg.output.emoji)

    lint_ctx = LintingContext(
        workspaces=workspaces,
        all_files=all_files,
        suites=suites,
        exec_cfg=cfg.execution,
        output_cfg=cfg.output,
        file_cfg=cfg.file_discovery,
        cfg=cfg,
    )
    all_outcomes = _run_linters_in_workspaces(lint_ctx)

    processing_ctx = ProcessingContext(
        outcomes=all_outcomes,
        files=all_files,
        output_cfg=cfg.output,
        dedupe_cfg=cfg.dedupe,
        exec_cfg=cfg.execution,
    )
    return _process_results_and_artifacts(processing_ctx)


# Install entrypoint wrapper kept from previous design
def perform_install_entrypoint(
    workspaces: list[Workspace],
    suites: list[LanguageSuite],
    files: list[Path],
    cfg: OutputConfig,
    *,
    install_and_run: bool,
) -> int | None:
    if suites:
        for s in suites:
            ok(f"Enabled suite: {s.name}", use_emoji=cfg.emoji)
    else:
        warn("No language suites detected — nothing to install.", use_emoji=cfg.emoji)
        return 0
    perform_install(workspaces, suites, files, cfg)
    if not install_and_run:
        ok("Install-only mode complete.", use_emoji=cfg.emoji)
        return 0
    return None


if __name__ == "__main__":
    MAIN_EXIT_CODE = 1
    try:
        MAIN_EXIT_CODE = main()
    except Exception:
        import traceback

        traceback.print_exc()
        fail("An unexpected error occurred. See traceback above.", use_emoji=True)
    sys.exit(MAIN_EXIT_CODE)
