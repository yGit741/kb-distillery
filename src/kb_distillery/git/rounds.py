"""Round issues: one GitHub issue (label `round`) tracks a multi-PR effort.

Body = a marker line + one checklist line per feature:

    <!-- kb-round v1 -->
    - [ ] round-issues
    - [x] merge-queue (#121)

`ship start <f> --round R` stores R in git config (`branch.infra/<f>.kbRound`, shared by all worktrees);
`ship pr` writes `Round: #R` into the PR body and posts `claimed` on the issue too; `merged`/`deployed`
tick the feature's line and post the event line on the issue. Everything here is best-effort: it prints
a note and returns, never raising into ship.
"""
import json
import re

from kb_distillery.git import events

LABEL = "round"
MARKER = "<!-- kb-round v1 -->"
TICK_EVENTS = ("merged", "deployed")
ROUND_LINE_RE = re.compile(r"^Round: #(\d+)\s*$", re.M)
_ITEM_RE = re.compile(r"^- \[( |x)\] ([a-z0-9][a-z0-9-]*)(.*)$", re.M)


def render_body(title, features):
    return "\n".join([MARKER, "", f"Round: {title}", "", *[f"- [ ] {f}" for f in features], ""])


def checklist(body):
    """[(feature, done, rest)] in body order."""
    return [(m.group(2), m.group(1) == "x", m.group(3).strip()) for m in _ITEM_RE.finditer(body or "")]


def tick(body, feature, pr=None):
    """Body with `feature` checked (appending `(#pr)`); a missing feature is appended checked."""
    suffix = f" (#{pr})" if pr else ""
    done = False

    def repl(m):
        nonlocal done
        if m.group(2) != feature or done:
            return m.group(0)
        done = True
        rest = m.group(3) if (not suffix or suffix.strip() in m.group(3)) else suffix + m.group(3)
        return f"- [x] {feature}{rest}"

    out = _ITEM_RE.sub(repl, body or "")
    if not done:
        out = out.rstrip("\n") + f"\n- [x] {feature}{suffix}\n"
    return out


def _config_key(branch):
    return f"branch.{branch}.kbRound"


def set_branch_round(branch, number, root):
    from kb_distillery.ops.daily_sync import run_git
    return run_git(["config", _config_key(branch), str(number)], cwd=root).returncode == 0


def branch_round(branch, root):
    from kb_distillery.ops.daily_sync import run_git
    v = run_git(["config", "--get", _config_key(branch)], cwd=root).stdout.strip()
    return int(v) if v.isdigit() else None


def round_from_pr_body(body):
    m = ROUND_LINE_RE.search(body or "")
    return int(m.group(1)) if m else None


def cmd_open(title, features, root=None):
    feats = [f.strip() for f in features.split(",") if f.strip()] if isinstance(features, str) else list(features)
    if not feats:
        print("error: --features a,b,c needs at least one feature")
        return 1
    events._gh(["label", "create", LABEL, "--force", "--color", "5319E7",
                "--description", "multi-PR effort (pixi run ship -- round status N)"], root)
    cp = events._gh(["issue", "create", "--title", title, "--label", LABEL,
                     "--body", render_body(title, feats)], root)
    m = re.search(r"/issues/(\d+)", cp.stdout or "")
    if cp.returncode != 0 or not m:
        print(f"error: could not open the round issue — {(cp.stderr or cp.stdout).strip()[:200]}")
        return 1
    print(f"#{m.group(1)} {title} {cp.stdout.strip()}")
    return 0


def _issue_body(number, root):
    cp = events._gh(["issue", "view", str(number), "--json", "body"], root)
    if cp.returncode != 0:
        return None
    try:
        return json.loads(cp.stdout).get("body") or ""
    except ValueError:
        return None


def post_event(number, event, sha="", root=None, **kv):
    """Comment a kb-event line on the round issue (gh issue comment). Never raises."""
    try:
        body = events.format_event(event, sha, **kv)
        cp = events._gh(["issue", "comment", str(number), "--body", body], root)
        if cp.returncode != 0:
            print(f"note: round #{number}: {event} event not posted — {(cp.stderr or cp.stdout).strip()[:200]}")
        return cp.returncode == 0
    except Exception as e:  # best-effort
        print(f"note: round #{number}: {event} event not posted — {e}")
        return False


def on_event(round_no, feature, event, sha="", pr=None, root=None, **kv):
    """Mirror a PR event on the round issue; tick the feature's line on merged/deployed. Never raises."""
    if not round_no:
        return False
    try:
        ok = post_event(round_no, event, sha, root, feature=feature, pr=pr, **kv)
        if event in TICK_EVENTS:
            body = _issue_body(round_no, root)
            if body is None:
                print(f"note: round #{round_no}: could not read the issue to tick {feature}")
                return False
            new = tick(body, feature, pr)
            if new != body:
                cp = events._gh(["issue", "edit", str(round_no), "--body", new], root)
                if cp.returncode != 0:
                    print(f"note: round #{round_no}: could not tick {feature} — {(cp.stderr or cp.stdout).strip()[:200]}")
                    return False
        return ok
    except Exception as e:  # best-effort: never fail ship
        print(f"note: round #{round_no}: {event} not mirrored — {e}")
        return False


def status_lines(body, evs):
    latest = {}
    for e in evs:
        f = e["kv"].get("feature")
        if f:
            latest[f] = e
    out = []
    for feat, done, rest in checklist(body):
        e = latest.get(feat)
        tail = f"{e['event']} {e['ts']}" + (f" pr=#{e['kv']['pr']}" if e["kv"].get("pr") else "") if e else "-"
        done = done or any(x["kv"].get("feature") == feat and x["event"] in TICK_EVENTS for x in evs)
        out.append(f"[{'x' if done else ' '}] {feat:<24} {tail}")  # events are the truth; the box may lag a race
    return out


def cmd_status(number, root=None):
    body = _issue_body(number, root)
    if body is None:
        print(f"error: could not read round #{number}")
        return 1
    if MARKER not in body:
        print(f"note: #{number} has no kb-round marker")
    evs = events.read(number, root)
    if not evs:
        print(f"note: no kb-events read on #{number} (none yet, or gh failed)")
    lines = status_lines(body, evs)
    print(f"round #{number}: {sum(l.startswith('[x]') for l in lines)}/{len(lines)} done")
    for line in lines:
        print(line)
    return 0


def parse_moved(items):
    """['feature=note', ...] -> {feature: note}; raises ValueError on a malformed item."""
    out = {}
    for it in items or []:
        feat, sep, note = it.partition("=")
        if not sep or not feat.strip() or not note.strip():
            raise ValueError(f"--moved needs feature=note, got {it!r}")
        out[feat.strip()] = note.strip()
    return out


def close_comment(merged, moved, note=""):
    lines = [f"Round closed: {len(merged)} merged feature(s)."]
    lines += [f"- merged: {f}" for f in merged]
    lines += [f"- moved: {f} -- {n}" for f, n in moved.items()]
    if note:
        lines += ["", note]
    return "\n".join(lines)


def cmd_close(number, moved_items=None, note="", root=None):
    """Close a round issue once every feature is merged or named in --moved. Idempotent on a closed issue."""
    try:
        moved = parse_moved(moved_items)
    except ValueError as e:
        print(f"error: {e}")
        return 2
    cp = events._gh(["issue", "view", str(number), "--json", "body,labels,state"], root)
    try:
        info = json.loads(cp.stdout) if cp.returncode == 0 else None
    except ValueError:
        info = None
    if not info:
        print(f"error: could not read round #{number}")
        return 1
    if LABEL not in [l.get("name") for l in info.get("labels") or []]:
        print(f"error: #{number} does not carry the `{LABEL}` label; refusing to close it")
        return 1
    if str(info.get("state", "")).upper() == "CLOSED":
        print(f"round #{number} is already closed; nothing to do")
        return 0
    body = info.get("body") or ""
    items = checklist(body)
    if not items:
        print(f"error: #{number} has no round checklist")
        return 1
    evs = events.read(number, root)
    merged_evs = {e["kv"].get("feature") for e in evs if e["event"] in TICK_EVENTS}
    merged = [f for f, done, _ in items if done or f in merged_evs]
    open_feats = [f for f, _, _ in items if f not in merged]
    unknown = [f for f in moved if f not in [i[0] for i in items]]
    if unknown:
        print(f"error: --moved names features not in round #{number}: {', '.join(unknown)}")
        return 1
    unfinished = [f for f in open_feats if f not in moved]
    if unfinished:
        print(f"error: round #{number} has unfinished features, neither merged nor --moved: {', '.join(unfinished)}")
        print('       re-run with --moved "<feature>=<note>" for each')
        return 1
    moved = {f: moved[f] for f in open_feats if f in moved}
    cc = events._gh(["issue", "comment", str(number), "--body", close_comment(merged, moved, note)], root)
    if cc.returncode != 0:
        print(f"error: could not comment on #{number} — {(cc.stderr or cc.stdout).strip()[:200]}")
        return 1
    cl = events._gh(["issue", "close", str(number)], root)
    if cl.returncode != 0:
        print(f"error: commented but could not close #{number} — {(cl.stderr or cl.stdout).strip()[:200]}")
        return 1
    print(f"closed round #{number}: {len(merged)} merged, {len(moved)} moved")
    return 0
