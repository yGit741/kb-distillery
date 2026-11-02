"""kb_distillery.config.resources: package_root / resource / root_resource / repo_root, lazy and shape-independent."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kb_distillery.config import resources


def _fake_checkout(tmp: Path, git: bool = True) -> Path:
    pkg = tmp / "repo" / "src" / "kb_distillery"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (tmp / "repo" / "pyproject.toml").write_text("[project]\nname='x'\n")
    if git:
        (tmp / "repo" / ".git").write_text("gitdir: elsewhere\n")      # a linked worktree has a .git FILE
    return pkg


def test_package_root_is_the_package_folder():
    root = resources.package_root()
    assert root.name == "kb_distillery" and (root / "__init__.py").is_file()


def test_this_checkout_is_found_from_its_package():
    repo = resources.repo_root()
    assert repo is not None and (repo / "pyproject.toml").is_file()
    assert resources.package_root() == repo / "src" / "kb_distillery"


def test_a_package_in_site_packages_has_no_repo_even_inside_a_repo(tmp_path):
    site = tmp_path / "proj" / ".venv" / "lib" / "python3.11" / "site-packages" / "kb_distillery"
    site.mkdir(parents=True)
    (tmp_path / "proj" / ".git").mkdir()
    (tmp_path / "proj" / "pyproject.toml").write_text("")
    with patch.object(resources, "package_root", lambda: site):
        assert resources.repo_root() is None


def test_a_src_layout_without_git_is_not_a_checkout(tmp_path):
    """An exported tree (no .git) is not a repository to ship from."""
    pkg = _fake_checkout(tmp_path, git=False)
    with patch.object(resources, "package_root", lambda: pkg):
        assert resources.repo_root() is None


def test_a_worktree_or_clone_is_a_checkout(tmp_path):
    pkg = _fake_checkout(tmp_path)
    with patch.object(resources, "package_root", lambda: pkg):
        assert resources.repo_root() == tmp_path / "repo"


def test_require_repo_root_names_the_problem_when_installed(tmp_path):
    site = tmp_path / "site-packages" / "kb_distillery"
    site.mkdir(parents=True)
    with patch.object(resources, "package_root", lambda: site):
        with pytest.raises(resources.NotInCheckout, match="ship works on a kb-distillery checkout"):
            resources.require_repo_root("ship")


def test_resource_is_relative_to_the_package_and_never_raises():
    assert resources.resource("llm/prompts").is_dir()
    missing = resources.resource("no/such/thing")
    assert missing == resources.package_root() / "no" / "such" / "thing" and not missing.exists()


def test_root_resource_reads_the_checkout_here_and_the_packed_copy_in_a_wheel(tmp_path):
    assert resources.root_resource("scripts") == resources.repo_root() / "scripts"
    site = tmp_path / "site-packages" / "kb_distillery"
    (site / "_data" / "scripts").mkdir(parents=True)
    with patch.object(resources, "package_root", lambda: site):
        assert resources.root_resource("scripts") == site / "_data" / "scripts"
        assert resources.root_resource("elsewhere") == site / "_data" / "elsewhere"      # missing: still a path


def test_a_packed_copy_wins_over_the_checkout(tmp_path):
    pkg = _fake_checkout(tmp_path)
    (pkg / "_data" / "scripts").mkdir(parents=True)
    (tmp_path / "repo" / "scripts").mkdir()
    with patch.object(resources, "package_root", lambda: pkg):
        assert resources.root_resource("scripts") == pkg / "_data" / "scripts"


def test_importing_the_package_needs_no_repo():
    """Nothing resolves a repository at import: with no checkout at all, kbconfig and paths still import."""
    code = ("from kb_distillery.config import resources\n"
            "resources.repo_root = lambda: None\n"
            "import kb_distillery.config.paths as p, kb_distillery.config.kb as k\n"
            "assert k.checkout_root() is None and k.primary_root() is None\n"
            "print(p.ROOT)\n")
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT", "KB_BASES_DIR")}
        env["KB_DISTILLERY_HOME"] = os.path.join(tmp, "home")
        cp = subprocess.run([sys.executable, "-c", code], cwd=tmp, env=env, capture_output=True, text=True)
        assert cp.returncode == 0, cp.stderr
        assert os.path.realpath(cp.stdout.strip()) == os.path.realpath(tmp)
