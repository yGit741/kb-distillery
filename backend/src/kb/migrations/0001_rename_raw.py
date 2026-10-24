"""Baseline: origin-based names for non-paper raw files (meta/raw-renames.tsv).

Already applied before migrations existed (schema 0.7); recorded in applied.tsv so
the runner treats it as done. Kept as the template for future migrations:
PRODUCES is the SCHEMA_VERSION after it runs, apply() must be idempotent.
"""
import os
import subprocess
import sys

PRODUCES = (0, 7)


def apply(root):
    subprocess.run([sys.executable, "-m", "kb.maintenance.rename_raw", "--apply"], cwd=root, check=True)
