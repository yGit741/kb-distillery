"""Turn a show-me script (JSON) into links that play it: the local app and the deployed private site.

    pixi run show -- demo.json            # prints both links
    pixi run show -- demo.json --open     # also opens the local one

A show-me is how an agent explains something on screen instead of in chat (skill `guided-tour`, § Show-me).
The script rides in the link (`?show=<base64url JSON>`), so nothing is registered, committed or deployed.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import webbrowser
from pathlib import Path

from kb_distillery.config.paths import ROOT

LOCAL = "http://127.0.0.1:8765/app"
KINDS = {"focus", "new", "changed", "issue"}
ACTIONS = {"click", "hover", "type", "press", "wait"}


def check(script) -> list[str]:
    """Problems that would make the script fail quietly in the browser."""
    if not isinstance(script, dict):
        return ["the script must be a JSON object with title and steps"]
    errs = []
    if not isinstance(script.get("title"), str) or not script["title"].strip():
        errs.append("title: required")
    if "autoplay" in script and not isinstance(script["autoplay"], (int, float)):
        errs.append("autoplay: ms per step, a number")
    steps = script.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["steps: at least one"]
    sel = lambda v: isinstance(v, str) and v.strip()  # noqa: E731
    for n, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            errs.append(f"step {n}: must be an object")
            continue
        for f in ("title", "body"):
            if not sel(s.get(f)):
                errs.append(f"step {n}: {f} required")
        if n == 1 and "go" not in s:
            errs.append("step 1: go required (the screen the link opens on, e.g. /graph)")
        if "go" in s and not str(s["go"]).startswith("/"):
            errs.append(f"step {n}: go must be an app path like /graph")
        if "target" in s and not sel(s["target"]):
            errs.append(f"step {n}: target must be a CSS selector")
        if "dim" in s and not (isinstance(s["dim"], (int, float)) and 0 <= s["dim"] <= 0.85):
            errs.append(f"step {n}: dim must be 0–0.85")
        marks = s.get("marks", [])
        for m in marks if isinstance(marks, list) else [marks]:
            if not isinstance(m, dict) or not sel(m.get("target")):
                errs.append(f"step {n}: mark {m!r} needs a target selector")
            elif m.get("kind") is not None and m["kind"] not in KINDS:
                errs.append(f"step {n}: kind {m['kind']!r} not in {sorted(KINDS)}")
        if s.get("kind") is not None and s["kind"] not in KINDS:
            errs.append(f"step {n}: kind {s['kind']!r} not in {sorted(KINDS)}")
        acts = s.get("do", [])
        for a in acts if isinstance(acts, list) else [acts]:
            if not isinstance(a, dict) or not (set(a) & ACTIONS):
                errs.append(f"step {n}: action {a!r} has none of {sorted(ACTIONS)}")
            elif any(k in a and not sel(a[k]) for k in ("click", "hover", "type")):
                errs.append(f"step {n}: action {a!r} needs a selector")
    return errs


def encode(script: dict) -> str:
    raw = json.dumps(script, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def deployed_url() -> str | None:
    """From the last deploy's status; a worktree has no .cache, so the primary checkout's is tried too."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    for root in (Path(ROOT), Path(common).parent if common else None):
        try:
            return json.loads((root / ".cache/share/status.json").read_text()).get("url")
        except (OSError, ValueError, TypeError):
            continue
    return None


def links(script: dict) -> dict[str, str]:
    start = script["steps"][0].get("go", "/")
    sep = "&" if "?" in start else "?"
    code = encode(script)
    out = {"local": f"{LOCAL}{start}{sep}show={code}"}
    if url := deployed_url():
        out["deployed"] = f"{url.rstrip('/')}{start}{sep}show={code}"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="show", description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument("--open", action="store_true", help="open the local link in the browser")
    a = ap.parse_args(argv)
    try:
        script = json.loads(a.file.read_text())
    except (OSError, ValueError) as e:
        print(f"show: cannot read {a.file}: {e}", file=sys.stderr)
        return 2
    if errs := check(script):
        print("\n".join(f"show: {e}" for e in errs), file=sys.stderr)
        return 2
    ls = links(script)
    for k, v in ls.items():
        print(f"{k}: {v}")
    if a.open:
        webbrowser.open(ls["local"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
