"""Flag test matrix (kb.flags.coverage), the pytest `flag` marker and the expiry lint (lint.check_flags)."""
import datetime as dt
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from kb.flags import coverage, value
from kb.flags.registry import load
from kb.lint import lint


def registry(root: Path, *flags):
    body = ""
    for name, created, expires in flags:
        body += textwrap.dedent(f"""
            [[flag]]
            name = "{name}"
            description = "d"
            owner = "alice"
            created = {created}
            expires = {expires}
            kind = "runtime"
            default = false
            envs = {{ local = false, private = false, public = false }}
            """)
    p = root / "meta" / "flags.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


# fixture sources are assembled so the repo-wide scan does not read this file's fake flag names
PY, TS = "@pytest." "mark" ".flag(", "with" "Flag("

# -- coverage --------------------------------------------------------------------------------------

def test_coverage_needs_both_states(tmp_path, capsys):
    reg = registry(tmp_path, ("a.one", "2026-01-01", "2027-01-01"), ("b.two", "2026-01-01", "2027-01-01"))
    write(tmp_path, "backend/tests/x/test_a.py", PY + '"a.one", True)\n' + PY + '"a.one", False)\n')
    write(tmp_path, "frontend/src/b.test.tsx", TS + '"b.two", true, () => 1)\n')
    assert coverage.main(["--flags", str(reg)], root=tmp_path) == 1
    out = capsys.readouterr().err
    assert "b.two: off" in out and "a.one" not in out
    write(tmp_path, "frontend/src/c.test.ts", TS + '\n  "b.two",\n  false, fn)\n')
    assert coverage.main(["--flags", str(reg)], root=tmp_path) == 0


def test_coverage_notes_unknown_names(tmp_path, capsys):
    reg = registry(tmp_path, ("a.one", "2026-01-01", "2027-01-01"))
    write(tmp_path, "frontend/src/a.test.ts", TS + '"a.one", true, f); ' + TS + '"a.one", false, f); ' + TS + '"gone", true, f)')
    assert coverage.main(["--flags", str(reg)], root=tmp_path) == 0  # a note, not a failure
    assert "gone" in capsys.readouterr().err


def test_coverage_ignores_non_test_files(tmp_path):
    registry(tmp_path, ("a.one", "2026-01-01", "2027-01-01"))
    write(tmp_path, "frontend/src/a.ts", TS + '"a.one", true, f); ' + TS + '"a.one", false, f)')
    assert coverage.missing(["a.one"], coverage.scan(tmp_path)) == ["a.one: on", "a.one: off"]


def test_repo_flags_are_covered():
    assert coverage.main([]) == 0


# -- pytest marker ---------------------------------------------------------------------------------

@pytest.mark.flag("screen.share", True)
def test_marker_forces_on():
    assert value("screen.share", "public") is True
    assert load().value("screen.share", "local") is True


@pytest.mark.flag("screen.share", False)
def test_marker_forces_off():
    assert value("screen.share", "private") is False


def test_marker_is_scoped_to_its_test():
    assert value("screen.share", "private") is True and value("screen.share", "public") is False


# -- expiry lint -----------------------------------------------------------------------------------

@pytest.fixture
def collected():
    with mock.patch.object(lint, "errors", []) as errs, mock.patch.object(lint, "warnings", []) as warns:
        yield errs, warns


def test_lint_expired_errors_expiring_warns(tmp_path, collected):
    errs, warns = collected
    today = dt.date(2026, 10, 25)
    p = registry(tmp_path, ("old.one", "2026-01-01", "2026-10-24"), ("soon.one", "2026-01-01", "2026-11-08"),
                 ("fine.one", "2026-01-01", "2026-11-09"))
    lint.check_flags(str(p), today)
    assert len(errs) == 1 and "old.one expired" in errs[0] and "owner alice" in errs[0]
    assert "flag-cleanup PR template" in errs[0]
    assert len(warns) == 1 and "soon.one expires in 14 day" in warns[0] and "owner alice" in warns[0]


def test_lint_invalid_registry_errors(tmp_path, collected):
    errs, _ = collected
    p = registry(tmp_path, ("Bad Name", "2026-01-01", "2027-01-01"))
    lint.check_flags(str(p))
    assert len(errs) == 1 and errs[0].startswith("meta/flags.toml: ") and "\n" not in errs[0]


def test_lint_missing_registry_is_silent(tmp_path, collected):
    lint.check_flags(str(tmp_path / "nope.toml"))
    assert collected == ([], [])
