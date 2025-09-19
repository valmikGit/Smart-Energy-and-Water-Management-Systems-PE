#!/usr/bin/env python3
"""
Cleanup script for scatter plot pipeline.

This script removes:
  - Temporary files (*.tmp, *.temp) from:
        - System temp directory
        - Base project directory
  - (Optional) previously generated scatter plots inside 'outputs_scatter' folder

Run this separately from the plotting script.
"""

import os
import glob
import tempfile
import shutil

# ------------------------------
# Config
# ------------------------------
BASE_PATH = "./"   # adjust if needed
OUTPUT_DIR = "outputs_scatter"

# ------------------------------
# Cleanup temp files (.tmp/.temp)
# ------------------------------
def cleanup_temp_files(base_dirs=None):
    if base_dirs is None:
        base_dirs = [tempfile.gettempdir(), BASE_PATH]
    patterns = ["*.tmp", "*.temp"]
    removed = 0
    for d in base_dirs:
        for pat in patterns:
            for f in glob.glob(os.path.join(d, pat)):
                try:
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
# Cleanup output scatter plots
# ------------------------------
def cleanup_output_dir(output_dir=OUTPUT_DIR):
    if not os.path.exists(output_dir):
        print(f"[CLEANUP] Output folder '{output_dir}' does not exist.")
        return
    removed = 0
    for f in glob.glob(os.path.join(output_dir, "*.png")):
        try:
            os.remove(f)
            removed += 1
            print(f"[CLEANUP] Removed scatter plot: {f}")
        except Exception as e:
            print(f"[CLEANUP] Could not remove {f}: {e}")
    if removed == 0:
        print(f"[CLEANUP] No scatter plots found in '{output_dir}'.")
    else:
        print(f"[CLEANUP] Removed {removed} scatter plots from '{output_dir}'.")

# ------------------------------
# Main
# ------------------------------
if __name__ == "__main__":
    print("[INFO] Starting cleanup...")

    # 1) Remove temp files
    cleanup_temp_files([tempfile.gettempdir(), BASE_PATH])

    # 2) Remove old scatter plots
    cleanup_output_dir(OUTPUT_DIR)

    print("\n[SUCCESS] Cleanup complete.")