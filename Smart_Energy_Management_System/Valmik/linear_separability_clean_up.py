#!/usr/bin/env python3
"""
cleanup_temp_files.py

Standalone script to clean up intermediate/temporary files.

This script:
 - Scans both the system temporary directory and the project base path.
 - Removes files matching common temp patterns (*.tmp, *.temp, tmp*).
 - Prints which files were removed, or reports if none were found.
"""

import os
import glob
import tempfile

# ------------------------------
# Config
# ------------------------------
# Base path of your project (adjust if needed)
BASE_PATH = "./"

# Patterns of temp files to clean
PATTERNS = ["*.tmp", "*.temp", "tmp*"]

# ------------------------------
# Cleanup function
# ------------------------------
def cleanup_temp_files(base_dirs=None):
    """
    Remove temporary files matching patterns from given directories.
    Default: system temp directory and BASE_PATH.
    """
    if base_dirs is None:
        base_dirs = [tempfile.gettempdir(), BASE_PATH]

    removed = 0
    for d in base_dirs:
        for pat in PATTERNS:
            for f in glob.glob(os.path.join(d, pat)):
                try:
                    if os.path.isfile(f):
                        os.remove(f)
                        removed += 1
                        print(f"[CLEANUP] Removed temp file: {f}")
                except Exception as e:
                    print(f"[CLEANUP] Could not remove {f}: {e}")

    if removed == 0:
        print("[CLEANUP] No temp files found to remove.")
    else:
        print(f"[CLEANUP] Removed {removed} temp files.")

# ------------------------------
# Main
# ------------------------------
if __name__ == "__main__":
    print("== Temp Files Cleanup ==")
    cleanup_temp_files()
    print("== Done ==")