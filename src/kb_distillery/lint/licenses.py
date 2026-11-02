"""Licence gate: no GPL / LGPL / AGPL package in the environment unless it is allowlisted here with a reason.

`python -m kb_distillery.lint.licenses` asks `pip-licenses` for every installed distribution and fails (exit 1) when a
licence string names the GPL family. This is how an AGPL dependency (PyMuPDF was one) cannot come back unnoticed.
Weak copyleft (MPL) and a missing licence field are listed but do not fail. `pixi run licenses` runs it; `ship` and CI
run it as a gate. To allow a package, add it to ALLOWED with a one-line reason a reviewer can check.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

COPYLEFT = re.compile(r"\b(?:A|L)?GPL\b|GNU (?:AFFERO |LESSER |LIBRARY )?(?:GENERAL PUBLIC|PUBLIC)", re.I)
WEAK = re.compile(r"\bMPL\b|Mozilla", re.I)

# distribution name (lower case) -> why it may stay
ALLOWED = {
    "mutagen": "GPL-2.0-or-later, pulled in by yt-dlp[default] to tag downloaded audio; used as an optional tool, never "
               "bundled or modified here",
}


def copyleft(row: dict) -> bool:
    """True when a licence string of the distribution names the GPL family. A dual licence is read as the user would."""
    return bool(COPYLEFT.search(row.get("License") or ""))


def check(rows: list, allowed: dict | None = None) -> tuple:
    """(violations, allowed_hits, weak, unknown) over `pip-licenses --format=json` rows."""
    allowed = ALLOWED if allowed is None else allowed
    bad, ok, weak, unknown = [], [], [], []
    for r in rows:
        name, lic = (r.get("Name") or "").lower(), r.get("License") or ""
        if copyleft(r):
            (ok if name in allowed else bad).append(r)
        elif WEAK.search(lic):
            weak.append(r)
        elif lic.strip().upper() in ("", "UNKNOWN"):
            unknown.append(r)
    return bad, ok, weak, unknown


def installed() -> list:
    out = subprocess.run([sys.executable, "-m", "piplicenses", "--from=mixed", "--format=json"],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit("licenses: pip-licenses failed — run: pixi install\n" + out.stderr.strip()[-400:])
    return json.loads(out.stdout)


def main() -> int:
    rows = installed()
    bad, ok, weak, unknown = check(rows)
    for r in ok:
        print(f"licenses: allowed {r['Name']} {r['Version']} ({r['License']}): {ALLOWED[r['Name'].lower()]}")
    for r in weak:
        print(f"licenses: note {r['Name']} {r['Version']} ({r['License']}): file-level copyleft, fine as a dependency")
    for r in unknown:
        print(f"licenses: note {r['Name']} {r['Version']} declares no licence")
    for r in bad:
        print(f"licenses: FAIL {r['Name']} {r['Version']}: {r['License']}", file=sys.stderr)
    if bad:
        print(f"licenses: {len(bad)} GPL-family package(s). Remove it, or allowlist it in "
              "kb_distillery/lint/licenses.py with a one-line reason.", file=sys.stderr)
        return 1
    print(f"licenses: {len(rows)} packages, no GPL-family licence outside the allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
