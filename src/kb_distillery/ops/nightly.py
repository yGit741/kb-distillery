"""The nightly entry point (`pixi run daily-sync`, the launchd job): runs `daily_sync.main`.

A module of its own because the `ops` package already imports `daily_sync` (through `core`), so running
`python -m kb_distillery.ops.daily_sync` makes Python warn that the module was loaded before it ran as __main__.

    python -m kb_distillery.ops.nightly [--dry-run] [--no-push]
"""
import sys

from kb_distillery.ops.daily_sync import main

if __name__ == "__main__":
    sys.exit(main())
