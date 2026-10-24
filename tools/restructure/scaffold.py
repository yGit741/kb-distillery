"""Create what the move needs besides the moved files: package markers, kb/paths.py, pyproject."""
import os

from layout import PKG, TESTS

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGES = ["", "core", "lint", "search", "git", "maintenance", "services", "migrations"]


def _tmpl(name):
    with open(os.path.join(HERE, "templates", name), encoding="utf-8") as f:
        return f.read()


def create(root, rep, dry):
    def put(rel, text, only_if_missing=True):
        path = os.path.join(root, rel)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if f.read() == text or only_if_missing:
                    return
        rep.moved.append(("(new)", rel))
        if not dry:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)

    for pkg in PACKAGES:
        put(f"{PKG}/{pkg}/__init__.py".replace("//", "/"), "")
    put("backend/src/kb/paths.py", _tmpl("paths.py"), only_if_missing=False)
    put("backend/pyproject.toml", _tmpl("pyproject.toml"), only_if_missing=False)
    put(f"{TESTS}/__init__.py", "")
    tdir = os.path.join(root, TESTS)
    if os.path.isdir(tdir):
        for d in sorted(os.listdir(tdir)):
            if os.path.isdir(os.path.join(tdir, d)) and d not in ("__pycache__", "fixtures"):
                put(f"{TESTS}/{d}/__init__.py", "")
