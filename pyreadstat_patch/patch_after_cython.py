#!/usr/bin/env python3
"""Patch pyreadstat after Cython compilation to handle UTF-8 encoding errors."""

import os
from pathlib import Path

source_dir = Path("/tmp/pyreadstat_source")

print("=" * 80)
print("POST-CYTHON UTF-8 ENCODING PATCH")
print("=" * 80)

# First regenerate the C files with Cython
print("🔄 Regenerating C files with Cython...")
os.chdir(source_dir)
result = os.system("python setup.py build_ext --inplace")
if result != 0:
    print("❌ Cython regeneration failed")
    exit(1)

print("✅ Cython regeneration complete")

# Now apply patches to the freshly generated files
files_to_patch = ["pyreadstat/_readstat_parser.c", "pyreadstat/_readstat_writer.c", "pyreadstat/pyreadstat.c"]

print("\n🔧 Applying UTF-8 patches to freshly generated C files...")

for file_path in files_to_patch:
    full_path = source_dir / file_path
    print(f"\n📝 Processing {file_path}")

    # Read the file
    with open(full_path) as f:
        content = f.read()

    # Apply the UTF-8 patch
    old_pattern = "#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, NULL)"
    new_pattern = '#define __Pyx_PyUnicode_FromStringAndSize(c_str, size) PyUnicode_DecodeUTF8(c_str, size, "replace")'

    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        print("   ✅ Applied UTF-8 'replace' error handling patch")

        # Write the patched content back
        with open(full_path, "w") as f:
            f.write(content)
        print(f"   💾 Saved patched {file_path}")
    else:
        print(f"   ⚠️  Pattern not found in {file_path}")

print("\n🔨 Rebuilding with patches...")
result = os.system("python setup.py build_ext --inplace")

if result == 0:
    print("✅ Rebuild successful with patches!")

    # Install in the test environment
    result = os.system(f"cd /tmp && source pyreadstat_env/bin/activate && cd {source_dir} && pip install .")
    if result == 0:
        print("✅ Patched pyreadstat installed!")
    else:
        print("❌ Failed to install patched version")
else:
    print("❌ Rebuild failed")

print("\n" + "=" * 80)
print("POST-CYTHON PATCH COMPLETE")
print("=" * 80)
