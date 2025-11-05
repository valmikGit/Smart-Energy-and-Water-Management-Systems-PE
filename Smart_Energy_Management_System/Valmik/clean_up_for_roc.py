#!/usr/bin/env python3
"""
Standalone cleanup script.

Removes temporary files (patterns: *.tmp, *.temp, tmp*) 
from the system temp directory.

Safe to run independently of training script.
"""

import os
import glob
import tempfile

def safe_remove(path: str):
    """Try to remove a file safely, log result."""
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"[CLEANUP] Removed: {path}")
    except Exception as e:
        print(f"[CLEANUP] Could not remove {path}: {e}")

def cleanup_temp_files():
    """Remove temporary files in system temp directory."""
    tmpdir = tempfile.gettempdir()
    print(f"[START CLEANUP] Looking in {tmpdir}")

    patterns = ["*.tmp", "*.temp", "tmp*"]
    total_removed = 0

    for pattern in patterns:
        for f in glob.glob(os.path.join(tmpdir, pattern)):
            safe_remove(f)
            total_removed += 1

    print(f"[CLEANUP] Completed. Total files removed: {total_removed}")

if __name__ == "__main__":
    cleanup_temp_files()