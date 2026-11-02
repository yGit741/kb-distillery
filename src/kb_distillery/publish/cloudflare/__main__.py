"""pixi run share -- <command>

    version                              one-line description + which modules are loaded

Subcommands are contributed by the modules in MODULES: each exposes
`register(subparsers)` and attaches `func(args) -> int` to its parser. A module
that does not exist yet is skipped silently, so build / deploy / snapshots can land
in separate PRs without touching this file.

Exit codes: 0 ok, 2 usage.
"""
import argparse
import importlib
import sys

MODULES = ["kb_distillery.publish.site.build", "kb_distillery.publish.cloudflare.deploy", "kb_distillery.publish.site.snapshots"]
DESCRIPTION = "Share the wiki graph + explorer as a self-contained HTML built from a git ref"


def load_modules(names=None):
    """Import the registry modules that exist; return {name: module}."""
    loaded = {}
    for name in names if names is not None else MODULES:
        try:
            loaded[name] = importlib.import_module(name)
        except ImportError as e:
            if getattr(e, "name", None) != name:
                raise
    return loaded


def build_parser(loaded):
    p = argparse.ArgumentParser(prog="share", description=DESCRIPTION)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("version", help="describe the tool and list loaded modules")
    v.set_defaults(func=lambda args: _version(loaded))
    for mod in loaded.values():
        mod.register(sub)
    return p


def _version(loaded):
    mods = ", ".join(n.rsplit(".", 1)[-1] for n in loaded) or "none"
    print(f"share: {DESCRIPTION}. modules: {mods}")
    return 0


def main(argv=None):
    loaded = load_modules()
    p = build_parser(loaded)
    args = p.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
