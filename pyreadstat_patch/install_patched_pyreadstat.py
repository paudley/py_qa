#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""
Install patched pyreadstat for complexify project.

This script patches pyreadstat to handle UTF-8 encoding errors in SPSS SAV files,
specifically fixing the 0x9a byte issue in WINDOWS-1252 encoded metadata.

Usage:
    cd ~/Active/complexify
    uv run python py-qa/pyreadstat_patch/install_patched_pyreadstat.py
"""

import os
from pathlib import Path
import sys

# Get paths
complexify_root = Path(__file__).parent.parent.parent
patch_dir = Path(__file__).parent
source_dir = patch_dir / "pyreadstat_source"

print("=" * 80)
print("COMPLEXIFY PYREADSTAT UTF-8 PATCH INSTALLER")
print("=" * 80)
print(f"Project root: {complexify_root}")
print(f"Source directory: {source_dir}")

if not source_dir.exists():
    print("❌ ERROR: pyreadstat source not found!")
    print(f"   Expected: {source_dir}")
    print("\nTry running the setup script first to download pyreadstat source.")
    sys.exit(1)

# Change to source directory
os.chdir(source_dir)
print(f"\n📂 Working directory: {os.getcwd()}")

# Step 1: Clean and regenerate C files
print("\n🔄 Step 1: Regenerating C files with Cython...")
result = os.system("python setup.py build_ext --inplace")
if result != 0:
    print("❌ Cython regeneration failed")
    sys.exit(1)
print("✅ Cython regeneration complete")

# Step 2: Apply UTF-8 patches
files_to_patch = ["pyreadstat/_readstat_parser.c", "pyreadstat/_readstat_writer.c", "pyreadstat/pyreadstat.c"]

print("\n🔧 Step 2: Applying UTF-8 patches to generated C files...")

patch_count = 0
for file_path in files_to_patch:
    full_path = source_dir / file_path
    print(f"\n📝 Processing {file_path}")

    if not full_path.exists():
        print(f"   ⚠️  File not found: {file_path}")
        continue

    # Read the file
    with open(full_path) as f:
        content = f.read()

    # Apply the UTF-8 patch
    old_pattern = "#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, NULL)"
    new_pattern = '#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, "replace")'

    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        patch_count += 1
        print("   ✅ Applied UTF-8 'replace' error handling patch")

        # Write the patched content back
        with open(full_path, "w") as f:
            f.write(content)
        print(f"   💾 Saved patched {file_path}")
    else:
        print(f"   ⚠️  Pattern not found in {file_path}")

if patch_count == 0:
    print("❌ ERROR: No patches were applied!")
    sys.exit(1)

print(f"\n✅ Applied {patch_count} patches successfully")

# Step 3: First rebuild to compile
print("\n🔨 Step 3: Initial rebuild...")
result = os.system("python setup.py build_ext --inplace")
if result != 0:
    print("❌ Initial rebuild failed")
    sys.exit(1)
print("✅ Initial rebuild complete")

# Step 3b: Re-apply patches after rebuild (Cython may have overwritten them)
print("\n🔧 Step 3b: Re-applying patches after rebuild...")
patch_count_final = 0
for file_path in files_to_patch:
    full_path = source_dir / file_path

    if not full_path.exists():
        continue

    # Read the file
    with open(full_path) as f:
        content = f.read()

    # Apply the UTF-8 patch
    old_pattern = "#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, NULL)"
    new_pattern = '#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, "replace")'

    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        patch_count_final += 1

        # Write the patched content back
        with open(full_path, "w") as f:
            f.write(content)
        print(f"   ✅ Re-applied patch to {file_path}")

print(f"✅ Re-applied {patch_count_final} final patches")

# Step 4: Install in complexify environment
print("\n📦 Step 4: Installing patched pyreadstat in complexify environment...")

# Change back to complexify root for proper uv context
os.chdir(complexify_root)
install_cmd = f"uv pip install {source_dir} --force-reinstall"
print(f"Running: {install_cmd}")

result = os.system(install_cmd)
if result == 0:
    print("✅ Patched pyreadstat installed in complexify environment!")
else:
    print("❌ Failed to install patched version")
    print("\nTrying alternative installation method...")
    result = os.system(f"cd {source_dir} && pip install . --force-reinstall")
    if result == 0:
        print("✅ Patched pyreadstat installed via pip!")
    else:
        print("❌ Installation failed completely")
        sys.exit(1)

# Step 5: Validation test
print("\n🧪 Step 5: Validation test...")
try:
    import pyreadstat

    print(f"✅ Pyreadstat imported successfully (version {pyreadstat.__version__})")

    # Test on the problematic SAV file
    sav_file = complexify_root / "datasets" / "gwp" / "Gallup_World_Poll_022125.sav"
    if sav_file.exists():
        print(f"🔬 Testing on: {sav_file}")
        df, meta = pyreadstat.read_sav(str(sav_file), metadataonly=True)
        print(f"✅ SUCCESS! Metadata read: {len(meta.column_names)} variables")
        print(f"   File encoding: {meta.file_encoding}")
        print(f"   First 5 variables: {meta.column_names[:5]}")
    else:
        print(f"⚠️  Test SAV file not found: {sav_file}")
        print("   Install successful, but cannot test without SAV file")

except Exception as e:
    print(f"❌ Validation failed: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("🎉 COMPLEXIFY PYREADSTAT PATCH INSTALLATION COMPLETE!")
print("🎉 SAV files with UTF-8 encoding issues can now be processed!")
print("=" * 80)
print("\nThe patched pyreadstat is now permanently installed in the complexify environment.")
print("You can run GWP data extraction without encoding errors.")
