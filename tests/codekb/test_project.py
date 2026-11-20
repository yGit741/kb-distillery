"""Project files and permalinks: GitHub and GitLab forms from the remote, credentials dropped, a custom pattern, no remote."""
import pytest

from kb_distillery.codekb.generic import project
from tests.codekb import repos


@pytest.mark.parametrize("remote, want", [
    ("https://github.com/octocat/hello.git", "https://github.com/octocat/hello"),
    ("git@github.com:octocat/hello.git", "https://github.com/octocat/hello"),
    ("ssh://git@gitlab.example.com:2222/group/sub/hello.git", "https://gitlab.example.com/group/sub/hello"),
    ("https://octocat:secret-token@gitlab.example.com/group/hello", "https://gitlab.example.com/group/hello"),
    ("", ""),
    ("/local/path/repo", ""),
])
def test_web_base(remote, want):
    assert project.web_base(remote) == want
    assert "secret" not in project.web_base(remote)


def make(tmp_path, repo_cfg, **extra):
    raw = {"name": "p", "repos": [repo_cfg], **extra}
    return project.from_dict(raw, tmp_path, "test")


def test_github_and_gitlab_forms(tmp_path):
    gh = make(tmp_path, {"name": "a", "path": "a", "git": False, "web": "https://github.com/octocat/a/blob/main", "role": "focus"})
    assert gh.permalink("a", "s", "x/y.py", 3) == "https://github.com/octocat/a/blob/main/x/y.py#L3"
    p = make(tmp_path, {"name": "a", "remote": "https://github.com/octocat/a.git", "path": "a"})
    assert p.permalink("a", "abc", "x/y.py", 3, 9) == "https://github.com/octocat/a/blob/abc/x/y.py#L3-L9"
    assert p.permalink("a", "abc", "x/y.py") == "https://github.com/octocat/a/blob/abc/x/y.py"
    assert p.permalink("a", "abc", "", kind="tree") == "https://github.com/octocat/a/tree/abc"
    assert p.change_url("a", 5) == "https://github.com/octocat/a/pull/5"
    p = make(tmp_path, {"name": "a", "remote": "git@gitlab.example.com:g/a.git", "path": "a"})
    assert p.repo("a").style == "gitlab"
    assert p.permalink("a", "abc", "x/y.py", 3, 9) == "https://gitlab.example.com/g/a/-/blob/abc/x/y.py#L3-9"
    assert p.permalink("a", "abc", "", kind="tree") == "https://gitlab.example.com/g/a/-/tree/abc"
    assert p.change_url("a", 5) == "https://gitlab.example.com/g/a/-/merge_requests/5"


def test_style_and_pattern_overrides(tmp_path):
    p = make(tmp_path, {"name": "a", "remote": "https://code.example.org/g/a", "style": "gitlab", "path": "a"})
    assert p.permalink("a", "abc", "f.py", 2) == "https://code.example.org/g/a/-/blob/abc/f.py#L2"
    p = make(tmp_path, {"name": "a", "remote": "https://code.example.org/g/a", "path": "a"},
             permalink={"blob": "{base}/src/{sha}/{path}", "range": "lines-{start}:{end}"})
    assert p.permalink("a", "abc", "f.py", 2, 4) == "https://code.example.org/g/a/src/abc/f.py#lines-2:4"


def test_no_remote_means_no_link(tmp_path):
    repos.python_repo(tmp_path / "a", remote="")
    p = make(tmp_path, {"name": "a"})
    assert p.permalink("a", "abc", "f.py", 2) == ""


def test_remote_read_from_the_checkout(tmp_path):
    repos.python_repo(tmp_path / "a", remote="https://octocat:tok@github.com/octocat/a.git")
    p = make(tmp_path, {"name": "a"})
    assert p.repo("a").web == "https://github.com/octocat/a"


@pytest.mark.parametrize("raw, message", [
    ({"repos": []}, "no `repos:`"),
    ({"repos": [{"name": "a", "role": "boss"}]}, "role must be"),
    ({"repos": [{"name": "a"}], "tiers": ["rust"]}, "unknown tier"),
    ({"repos": [{"name": "a b"}]}, "needs a `name`"),
    ({"repos": [{"name": "a", "style": "svn"}]}, "style must be"),
])
def test_bad_projects_say_why(tmp_path, raw, message):
    with pytest.raises(SystemExit, match=message):
        project.from_dict(raw, tmp_path, "test")


def test_kb_toml_table(tmp_path):
    (tmp_path / "kb.toml").write_text('[kb]\nname = "x"\n[code]\ntiers = ["python"]\n[[code.repos]]\nname = "core"\nrole = "focus"\npath = "src"\n', encoding="utf-8")
    p = project.load_kb(tmp_path)
    assert p.tiers == ("python",) and p.repo("core").path == (tmp_path / "src").resolve() and p.out == (tmp_path / ".local/code" / tmp_path.name).resolve()
    (tmp_path / "kb.toml").write_text('[kb]\nname = "x"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="no \\[code\\] table"):
        project.load_kb(tmp_path)


def test_environment_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_CODE_OUT", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("KB_CODE_REPO_OVERRIDE", f"a={tmp_path / 'old'}")
    p = make(tmp_path, {"name": "a"})
    assert p.out == tmp_path / "elsewhere" and p.repo("a").path == tmp_path / "old"
