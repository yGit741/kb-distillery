"""A temp kb repo with three pages for the proposals tests (the real kb is never read or written)."""
import os
from unittest import mock

import pytest

from kb_distillery.proposals import service
from tests.ops.test_view import ENV, git, make_repo

PAGE = ("---\ntype: idea\nlayer: concept\ndescription: About {n}.\n---\n\n# {n}\n\n"
        "The first claim is strong.\n\nA second paragraph links [Beta](beta.md).\n\n## Details\n\nMore text here.\n"
        "\n## My notes\n\nMine, keep me. [[gamma]]\n")


def write(root, slug, text=None):
    path = os.path.join(root, "wiki", slug + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text is not None else PAGE.format(n=slug))
    return path


def read(root, slug):
    with open(os.path.join(root, "wiki", slug + ".md"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def kb(tmp_path, monkeypatch):
    root = make_repo(str(tmp_path), gitignore="meta/.ops/\n.local/\n")
    for slug in ("alpha", "beta", "gamma"):
        write(root, slug)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: pages (retro)")
    monkeypatch.setenv("KB_PRIVACY_TERMS", "zorblaxquux")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(service, "DEFAULT_ROOT", root), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        yield root
