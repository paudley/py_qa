#!/usr/bin/env python3
"""Stub Python interpreter reporting version 3.11 and failing imports."""

from __future__ import annotations

import sys

CODE_ARG_INDEX = 1


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit("fake_py311 invoked without code")
    if args[0] != "-c":
        sys.exit("fake_py311 supports only '-c' invocations")
    if len(args) <= CODE_ARG_INDEX:
        sys.exit("fake_py311 requires code string")

    code = args[CODE_ARG_INDEX]

    if "sys.version_info" in code:
        sys.stdout.write("(3, 11)\n")
        return

    # For probe scripts we emit "missing" so the launcher falls back to uv.
    sys.stdout.write("missing")


if __name__ == "__main__":
    main()
