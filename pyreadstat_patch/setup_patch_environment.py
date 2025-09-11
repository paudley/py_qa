#!/usr/bin/env python3
"""
Setup script to download pyreadstat source for patching.

This script downloads the pyreadstat source code needed for applying
the UTF-8 encoding fix for SPSS SAV files.

Usage:
    cd ~/Active/complexify
    uv run python scripts/pyreadstat_patch/setup_patch_environment.py
    uv run python scripts/pyreadstat_patch/install_patched_pyreadstat.py
"""

import os
from pathlib import Path
import sys

# Get paths
patch_dir = Path(__file__).parent
source_dir = patch_dir / "pyreadstat_source"

print("=" * 80)
print("COMPLEXIFY PYREADSTAT PATCH ENVIRONMENT SETUP")
print("=" * 80)

# Check if source already exists
if source_dir.exists():
    print(f"✅ Pyreadstat source already exists: {source_dir}")
    print("   Use install_patched_pyreadstat.py to apply patches")
    sys.exit(0)

print(f"📥 Downloading pyreadstat source to: {source_dir}")

# Change to patch directory
os.chdir(patch_dir)

# Clone pyreadstat source
result = os.system("git clone https://github.com/Roche/pyreadstat.git pyreadstat_source")
if result != 0:
    print("❌ Failed to download pyreadstat source")
    print("\nAlternative: Download manually from https://github.com/Roche/pyreadstat")
    sys.exit(1)

print("✅ Pyreadstat source downloaded successfully!")

# Install build dependencies
print("\n📦 Installing build dependencies...")
os.chdir(source_dir)

# Install cython and other build deps
result = os.system("uv add cython numpy setuptools wheel")
if result != 0:
    print("❌ Failed to install build dependencies")
    print("   Try running: uv add cython numpy setuptools wheel")
    sys.exit(1)

print("✅ Build dependencies installed!")

print("\n" + "=" * 80)
print("🎉 SETUP COMPLETE!")
print("=" * 80)
print("\nNext steps:")
print("1. Run: uv run python scripts/pyreadstat_patch/install_patched_pyreadstat.py")
print("2. Test SAV file reading in your scripts")
print("\nThe patched pyreadstat will resolve UTF-8 encoding errors in SPSS SAV files.")
