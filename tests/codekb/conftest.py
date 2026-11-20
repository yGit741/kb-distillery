import os

import pytest

from tests.codekb import repos


@pytest.fixture(autouse=True)
def _git_env(monkeypatch):
    """Every git call (the fixtures' and the tool's own) runs as octocat with no global config."""
    for k, v in repos.ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("KB_CODE_REPOS", raising=False)
    monkeypatch.delenv("KB_CODE_OUT", raising=False)
    monkeypatch.delenv("KB_CODE_REPO_OVERRIDE", raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", os.path.dirname(os.path.realpath(__file__)))


@pytest.fixture
def py_project(tmp_path):
    """A project with one Python repo (github remote) and its project file."""
    from kb_distillery.codekb.generic import project
    repos.python_repo(tmp_path / "core")
    f = tmp_path / "project.yaml"
    f.write_text("name: demo\ntiers: [python]\nrepos:\n  - {name: core, role: focus}\n", encoding="utf-8")
    return project.load(f)


@pytest.fixture
def built(py_project):
    from kb_distillery.codekb import pipeline
    pipeline.build(py_project, quiet=True)
    pipeline.cards(py_project)
    return py_project
