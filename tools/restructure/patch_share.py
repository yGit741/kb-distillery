"""Patches for kb.share: the worker moved to top-level share/, the build must find old-layout viewers."""


def register(add):
    add("backend/src/kb/share/contracts.py",
        ("REPO = Path(__file__).resolve().parents[2]",
         "from kb.paths import CHECKOUT_ROOT\n\nREPO = Path(CHECKOUT_ROOT)   # the checkout this tool runs from (never $KB_ROOT)"))
    add("backend/src/kb/share/deploy.py",
        ('WORKER_DIR = Path(__file__).resolve().parent / "worker"',
         'WORKER_DIR = REPO / "share"      # the Cloudflare Worker sources (auth.js, admin.js, wrangler template)'))
    add("backend/src/kb/share/autodeploy.py",
        ('(root / "meta" / "share" / "deploy.py").is_file()',
         '(root / "backend" / "src" / "kb" / "share" / "deploy.py").is_file()'))
    add("backend/src/kb/share/build.py",
        ('def _meta_path():\n    """Import path for the sibling meta/ modules (commit_policy, ops)."""\n'
         '    meta = str(REPO / "meta")\n    return meta\n\n\n', ''),
        ('        _meta_path()\n', ''),
        ('    _meta_path()\n', ''),
        ('def archive(root, sha, dest, pathspec=()):',
         'APP_LAYOUT = "backend/src/kb/share/build.py"      # viewer code since the app layout (package kb)\n'
         'LEGACY_LAYOUT = "meta/share/build.py"             # refs before it: the code lived in meta/\n\n\n'
         'def viewer_layout(root, sha):\n'
         '    """"app" | "legacy" | None: which layout the viewer ref has (so any old ref can still render a page)."""\n'
         '    for probe, name in ((APP_LAYOUT, "app"), (LEGACY_LAYOUT, "legacy")):\n'
         '        cp = subprocess.run(["git", "cat-file", "-e", f"{sha}:{probe}"], cwd=str(root),\n'
         '                            capture_output=True, check=False)\n'
         '        if cp.returncode == 0:\n'
         '            return name\n'
         '    return None\n\n\n'
         'def archive(root, sha, dest, pathspec=()):'),
        ('        if viewer_worktree:\n            viewer_dir = str(viewer_root)\n        else:\n'
         '            viewer_dir = os.path.join(tmp, "viewer")\n'
         '            archive(viewer_root, viewer_sha, viewer_dir, ("meta",))\n'
         '        if not os.path.isfile(os.path.join(viewer_dir, "backend", "src", "kb", "share", "build.py")):\n'
         '            raise BuildError(',
         '        if viewer_worktree:\n            viewer_dir = str(viewer_root)\n'
         '            layout = "app" if os.path.isfile(os.path.join(viewer_dir, APP_LAYOUT)) else (\n'
         '                "legacy" if os.path.isfile(os.path.join(viewer_dir, LEGACY_LAYOUT)) else None)\n'
         '        else:\n'
         '            viewer_dir = os.path.join(tmp, "viewer")\n'
         '            layout = viewer_layout(viewer_root, viewer_sha)\n'
         '            if layout:\n'
         '                archive(viewer_root, viewer_sha, viewer_dir, ("backend",) if layout == "app" else ("meta",))\n'
         '        if layout is None:\n'
         '            raise BuildError('),
        ('has no backend/src/kb/share/build.py — "',
         'has no share builder (backend/src/kb/share/build.py, or meta/share/build.py before the app layout) — "'),
        ('        env.pop("PYTHONPATH", None)\n        env.pop(VERSIONS_ENV, None)',
         '        env.pop("PYTHONPATH", None)\n'
         '        if layout == "app":      # the viewer\'s own kb package, not whatever is installed\n'
         '            env["PYTHONPATH"] = os.path.join(viewer_dir, "backend", "src")\n'
         '        env.pop(VERSIONS_ENV, None)'),
        ('        cmd = [sys.executable, "-m", "kb.share.build", "--inner",',
         '        cmd = [sys.executable, "-m", "kb.share.build" if layout == "app" else "meta.share.build", "--inner",'))
    add("backend/src/kb/share/build.py",
        ('    """x of SCHEMA_VERSION = (x, y) in backend/src/kb/core/schema.py at `sha`, or None."""\n'
         '    cp = subprocess.run(["git", "show", f"{sha}:backend/src/kb/core/schema.py"], cwd=str(root), capture_output=True,\n'
         '                        text=True, check=False)\n'
         '    m = _SCHEMA_RE.search(cp.stdout or "") if cp.returncode == 0 else None\n'
         '    return int(m.group(1)) if m else None\n',
         '    """x of SCHEMA_VERSION = (x, y) in the schema at `sha` (backend/src/kb/core/schema.py, or meta/schema.py\n'
         '    before the app layout), or None."""\n'
         '    for rel in ("backend/src/kb/core/schema.py", "meta/schema.py"):\n'
         '        cp = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(root), capture_output=True,\n'
         '                            text=True, check=False)\n'
         '        m = _SCHEMA_RE.search(cp.stdout or "") if cp.returncode == 0 else None\n'
         '        if m:\n'
         '            return int(m.group(1))\n'
         '    return None\n'))
