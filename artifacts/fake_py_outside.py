#!/usr/bin/env python3
"""Stub interpreter reporting repo modules located outside the project."""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] != "-c":
        sys.exit("fake_py_outside expects '-c'")
    code = args[1]
    if "sys.version_info" in code:
        sys.stdout.write("(3, 12)\n")
        return
    sys.stdout.write("outside")


if __name__ == "__main__":
    main()
