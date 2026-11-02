"""The licence gate: a GPL-family package fails unless allowlisted with a reason; weak copyleft and unknowns only note."""
import subprocess
import sys

from kb_distillery.git import ship
from kb_distillery.lint import licenses


def row(name, lic, version="1.0"):
    return {"Name": name, "Version": version, "License": lic}


def test_agpl_gpl_and_lgpl_fail():
    rows = [row("pymupdf", "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"),
            row("a", "GPL-2.0-or-later"), row("b", "LGPL-2.1-only"), row("c", "GNU General Public License v3 (GPLv3)"),
            row("d", "AGPL-3.0-only")]
    bad, ok, _, _ = licenses.check(rows, allowed={})
    assert [r["Name"] for r in bad] == ["pymupdf", "a", "b", "c", "d"] and not ok


def test_permissive_licences_pass():
    rows = [row("x", "MIT"), row("y", "BSD-3-Clause"), row("z", "Apache-2.0 OR BSD-2-Clause"),
            row("p", "Apache Software License; BSD License"), row("q", "PSF-2.0")]
    assert licenses.check(rows, allowed={})[0] == []


def test_allowlisted_package_is_reported_not_failed():
    bad, ok, _, _ = licenses.check([row("Mutagen", "GPL-2.0-or-later")], allowed={"mutagen": "tags audio"})
    assert bad == [] and [r["Name"] for r in ok] == ["Mutagen"]


def test_weak_copyleft_and_unknown_do_not_fail():
    bad, _, weak, unknown = licenses.check([row("certifi", "Mozilla Public License 2.0 (MPL 2.0)"), row("g", "UNKNOWN")],
                                           allowed={})
    assert bad == [] and len(weak) == 1 and len(unknown) == 1


def test_every_allowlist_entry_has_a_reason():
    assert all(isinstance(why, str) and len(why) > 20 for why in licenses.ALLOWED.values())


def test_licenses_is_a_ship_gate():
    assert "licenses" in [name for name, _ in ship.GATES]


def test_the_environment_passes_the_gate():
    out = subprocess.run([sys.executable, "-m", "kb_distillery.lint.licenses"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
