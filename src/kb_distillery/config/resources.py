"""Where the package's own files are, and where the repository is (when there is one).

The engine runs in two shapes: installed from a wheel (`pip install kb-distillery`, no repository anywhere) and
from a checkout (`pixi run ...`, editable). Nothing may assume the second. Three functions, all lazy (nothing is
resolved at import, so `import kb_distillery` works in a clean venv):

    package_root()   the installed `kb_distillery` package folder
    resource(path)   a file or folder that ships inside the package (prompts, static, _webapp, ...)
    root_resource(path)  transitional: the root-level folders still outside the package (share, hooks)
    repo_root()      the git checkout the package lives in, or None for an installed copy;
                     `require_repo_root(what)` is the dev-only form that raises with a clear message

`resource()` is package data (the kits among it: `resource("kits/base/defaults")`). `root_resource()` is the
transitional lookup for the folders that still sit at the repository root (`share/`, `scripts/kb-hooks`):
`_data/<path>` in a wheel (pyproject.toml `force-include`), `<repo>/<path>` in a checkout. Lane C moved the skills into the
package as `kits/<kit>/skills`, moves the hooks next and then deletes `root_resource()`.
"""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

DATA_DIR = "_data"      # wheel-only folder holding the root-level folders force-included by pyproject.toml


class NotInCheckout(RuntimeError):
    """A developer-only feature was used from an installed package (there is no repository to work on)."""


def package_root() -> Path:
    """The `kb_distillery` package folder (an unzipped install, editable included)."""
    return Path(str(resources.files("kb_distillery")))


def repo_root() -> Path | None:
    """The checkout this code runs from, or None when it is an installed copy.

    A checkout is `<root>/src/kb_distillery` with `<root>/pyproject.toml` and a `.git` (a file in a linked
    worktree). A package inside some venv's site-packages never qualifies, even when that venv sits in a repo."""
    pkg = package_root()
    root = pkg.parent.parent
    if pkg.parent.name == "src" and (root / "pyproject.toml").is_file() and (root / ".git").exists():
        return root
    return None


def require_repo_root(what: str = "this command") -> Path:
    root = repo_root()
    if root is None:
        raise NotInCheckout(f"{what} works on a kb-distillery checkout, and kb_distillery is installed at "
                            f"{package_root()} (no repository). Clone the repository and run it from there.")
    return root


def resource(path: str) -> Path:
    """A file or folder that ships inside the package, by its path relative to it (`prompts`, `share/static`).
    Never raises: a missing resource returns the path it would have, so callers report the missing file by name."""
    return package_root() / path


def root_resource(path: str) -> Path:
    """TRANSITIONAL (deleted by Lane C, when `share/` and `scripts/kb-hooks`
    become package data under `kits/`): a folder that lives at the repository root in a checkout and under
    `_data/<path>` in a wheel (pyproject.toml `force-include`). Same path in both shapes. Never raises."""
    packed = package_root() / DATA_DIR / path
    if packed.exists():
        return packed
    root = repo_root()
    return root / path if root is not None else packed
