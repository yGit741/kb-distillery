"""Small fixture repositories for the codekb tests, built in a temp folder with `git init`: no network, no global git config."""
import os
import subprocess
from pathlib import Path

ENV = {"GIT_AUTHOR_NAME": "octocat", "GIT_AUTHOR_EMAIL": "me@example.com", "GIT_COMMITTER_NAME": "octocat",
       "GIT_COMMITTER_EMAIL": "me@example.com", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_DATE": "2026-01-02T10:00:00+0000", "GIT_COMMITTER_DATE": "2026-01-02T10:00:00+0000"}


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                          capture_output=True, text=True, check=True, env={**os.environ, **ENV}).stdout


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")


def commit(root: Path, message: str, files: dict[str, str]) -> None:
    write(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


UTIL = '''"""Helpers."""
import os


def slugify(text):
    """Lower-case a title."""
    return text.lower().replace(" ", "-")


def home():
    return os.environ.get("APP_HOME", "/tmp")
'''

APP = '''"""The app."""
import argparse
import json

from pkg import util
from pkg.util import slugify


class Base:
    pass


class Runner(Base):
    """Runs things."""

    def run(self, name):
        """Run one thing."""
        return util.slugify(name)

    def again(self, name):
        return self.run(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", help="talk more")
    args = ap.parse_args()
    return Runner().run(json.dumps(args.verbose)) + slugify("x")


if __name__ == "__main__":
    main()
'''


def python_repo(root: Path, remote: str = "https://github.com/octocat/core.git") -> Path:
    """Four commits and one merged pull request touching app.py and util.py together."""
    root.mkdir(parents=True)
    git(root, "init", "-q")
    commit(root, "first", {"pkg/__init__.py": "", "pkg/util.py": UTIL, "pkg/app.py": APP.replace("slugify(\"x\")", "'x'")})
    commit(root, "second", {"README.md": "# core\n", "pkg/other.py": "def other():\n    return 1\n"})
    git(root, "checkout", "-q", "-b", "feature")
    commit(root, "feature work", {"pkg/util.py": UTIL + "\n\ndef extra():\n    return 2\n", "pkg/app.py": APP})
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #7 from octocat/feature\n\nAdd the slug helper")
    commit(root, "third", {"pkg/other.py": "def other():\n    return 3\n", "pkg/util.py": UTIL + "\n\ndef extra():\n    return 3\n"})
    if remote:
        git(root, "remote", "add", "origin", remote)
    return root


FOO_H = '''#pragma once
namespace shapes {
/** A circle. */
class Circle {
public:
    explicit Circle(double r);
    double area() const;
    void grow(double by);
private:
    double r_;
};
}
'''

FOO_CPP = '''#include "foo.h"
namespace shapes {
Circle::Circle(double r) : r_(r) {}
double Circle::area() const { return 3.14 * r_ * r_; }
void Circle::grow(double by) { r_ += by; }
}
'''

MAIN_CPP = '''#include "foo.h"
#include <vector>

int main() {
    shapes::Circle c(1.0);
    c.grow(2.0);
    return static_cast<int>(c.area());
}
'''


def cpp_repo(root: Path, remote: str = "git@gitlab.example.com:group/native.git") -> Path:
    root.mkdir(parents=True)
    git(root, "init", "-q")
    commit(root, "init", {"include/foo.h": FOO_H, "src/foo.cpp": FOO_CPP})
    commit(root, "add main", {"src/main.cpp": MAIN_CPP})
    if remote:
        git(root, "remote", "add", "origin", remote)
    return root
