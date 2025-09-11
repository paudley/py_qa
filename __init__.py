"""This directory is not a Python package."""

raise ImportError(
    "The 'scripts' directory is not a Python package and should not be imported. "
    "This error is raised by scripts/__init__.py to prevent accidental imports "
    "of utility scripts or sub-modules."
)
