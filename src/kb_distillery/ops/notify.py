#!/usr/bin/env python3
"""Email the nightly report — every night (mode "digest") or only when something needs fixing ("problems").

    python3 -m kb_distillery.ops.notify --test          # one-line test email (says clearly when the keychain item is missing)
    python3 -m kb_distillery.ops.notify --show-config

Config: meta/ops/sync.toml `[notify]` (email, mode, on = severities, min_interval_hours).
The body is the nightly report Doc (src/kb_distillery/ops/nightly_report.py) as HTML with a plain-text
alternative; without a Doc (older callers) it falls back to the plain hygiene text.
Password: macOS keychain, `security find-generic-password -a <email> -s kb-distillery-gmail -w` (an item under the old name is still read)
— never printed, logged or committed. Sent over smtplib SSL to smtp.gmail.com:465 with the
configured address as both SMTP user and recipient. Nothing here ever raises: a missing
keychain item, an offline Mac or a refused login print one note and return False.
"""
import argparse
import datetime
import json
import os
import smtplib
import subprocess
import sys
import tomllib
from email.message import EmailMessage

from kb_distillery.config import userdir
from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.vault.schema import OPS_DIR

CONFIG_PATH = os.path.join("meta", "ops", "sync.toml")
LAST_SENT = "notify-last.json"          # under meta/.ops/ (gitignored ops runtime dir)
KEYCHAIN_SERVICE = "kb-distillery-gmail"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
SUBJECT_PREFIX = "[thesis-kb]"
DEFAULTS = {"email": "", "mode": "problems", "on": ["error", "warn"], "min_interval_hours": 20}
MODES = ("digest", "problems")


def load_config(root=ROOT):
    """`[notify]` of meta/ops/sync.toml merged over DEFAULTS (missing file → defaults, no email)."""
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(root, CONFIG_PATH), "rb") as f:
            cfg.update(tomllib.load(f).get("notify", {}))
    except FileNotFoundError:
        pass
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"notify: config unreadable ({e}) — using defaults")
    return cfg


def keychain_password(account, service=KEYCHAIN_SERVICE):
    """The app password from the login keychain, or None (never echoed)."""
    for name in userdir.keychain_services(service):         # the new name, then the one it replaces (read only)
        try:
            proc = subprocess.run(["security", "find-generic-password", "-a", account, "-s", name, "-w"],
                                  capture_output=True, text=True, check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        pw = proc.stdout.strip() if proc.returncode == 0 else ""
        if pw:
            return pw
    return None


def send_email(subject, body, to, password=None, smtp_cls=None, html=None):
    """Send one mail from `to` to `to` over Gmail SSL — plain text, plus an HTML alternative when
    `html` is given. True on success, False otherwise."""
    if not to:
        print("notify: no email configured in meta/ops/sync.toml — not sent")
        return False
    password = password or keychain_password(to)
    if not password:
        print(f"notify: no keychain item (account {to}, service {KEYCHAIN_SERVICE}) — not sent; "
              "see meta/automation-daily-sync.md § Email report")
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = to, to, subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with (smtp_cls or smtplib.SMTP_SSL)(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(to, password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        print(f"notify: email not sent — {type(e).__name__}: {e}")
        return False
    print(f"notify: sent {subject!r} to {to}")
    return True


# ---------- report → email ----------

def _last_sent_path(root):
    return os.path.join(root, OPS_DIR, LAST_SENT)


def _last_sent(root):
    try:
        with open(_last_sent_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _remember(root, fingerprint, now):
    path = _last_sent_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fingerprint, "at": now.isoformat(timespec="seconds")}, f)


def subject_for(report, sync_failed=False):
    kinds = report.kinds()
    n = len(report.findings)
    if sync_failed:
        head = "nightly sync FAILED" + (f" + {n} problem{'s' if n != 1 else ''}" if n else "")
    else:
        head = f"nightly: {n} problem{'s' if n != 1 else ''}"
    return f"{SUBJECT_PREFIX} {head}" + (f" ({', '.join(kinds[:4])}{', …' if len(kinds) > 4 else ''})" if kinds else "")


def body_for(report, sync_failed=False, log_tail=None, error=None, root=ROOT):
    parts = []
    if sync_failed:
        parts.append("The nightly sync did not finish cleanly." + (f"\n\n{error.rstrip()}" if error else ""))
    parts.append(report.text())
    if sync_failed and log_tail:
        parts.append("--- daily-sync log (last lines) ---\n" + log_tail.rstrip())
    parts.append(f"vault: {root}\nrun: {report.started}\nconfig: {CONFIG_PATH}")
    return "\n\n".join(parts) + "\n"


def log_tail(path, n=30):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def notify_report(report, root=ROOT, sync_failed=False, error=None, tail=None, cfg=None, now=None, send=None,
                  doc=None):
    """Decide and send. Returns "clean" | "throttled" | "sent" | "not-sent" (never raises).

    With a nightly-report `doc` and `mode = "digest"`, a clean night is mailed too; the throttle
    still keeps the same report from going out twice within `min_interval_hours`.
    `send` (subject, body, to[, html=]) -> bool is injectable for tests; default send_email.
    """
    cfg = cfg or load_config(root)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    wanted = set(cfg.get("on") or [])
    hits = [f for f in report.findings if f.severity in wanted]
    digest = doc is not None and cfg.get("mode") == "digest"
    if not hits and not sync_failed and not digest:
        return "clean"
    fingerprint = report.fingerprint()
    if sync_failed:
        last_line = (error or "").strip().splitlines()[-1:]
        fingerprint += "|sync-failed:" + (last_line[0] if last_line else "")
    last = _last_sent(root)
    interval = float(cfg.get("min_interval_hours") or 0)
    if last and last.get("fingerprint") == fingerprint and interval > 0:
        try:
            at = datetime.datetime.fromisoformat(last["at"])
            if at.tzinfo is None:
                at = at.replace(tzinfo=datetime.timezone.utc)
            if (now - at).total_seconds() < interval * 3600:
                print(f"notify: same report already sent at {last['at']} — not resent")
                return "throttled"
        except (KeyError, ValueError):
            pass
    if doc is not None:
        from kb_distillery.ops.nightly_report import subject
        from kb_distillery.ops.report import render_html, render_text
        ok = (send or send_email)(subject(doc, report, SUBJECT_PREFIX), render_text.render(doc), cfg.get("email", ""),
                                  html=render_html.render(doc))
    else:
        ok = (send or send_email)(subject_for(report, sync_failed), body_for(report, sync_failed, tail, error, root),
                                  cfg.get("email", ""))
    if ok:
        _remember(root, fingerprint, now)
    return "sent" if ok else "not-sent"


# ---------- CLI ----------

def main(argv=None):
    p = argparse.ArgumentParser(prog="notify", description="nightly email notifications")
    p.add_argument("--test", action="store_true", help="send a one-line test email")
    p.add_argument("--show-config", action="store_true")
    args = p.parse_args(argv)
    cfg = load_config(ROOT)
    if args.show_config or not args.test:
        print(f"email: {cfg['email'] or '(none)'}   mode: {cfg['mode']}   on: {', '.join(cfg['on'])}   "
              f"min_interval_hours: {cfg['min_interval_hours']}")
        print(f"keychain item: {'present' if keychain_password(cfg['email']) else 'MISSING — security add-generic-password -a ' + (cfg['email'] or '<email>') + ' -s ' + KEYCHAIN_SERVICE + ' -w <app-password> -U'}")
        if not args.test:
            return 0
    if not cfg["email"]:
        print("notify: set [notify] email in meta/ops/sync.toml first")
        return 1
    if not keychain_password(cfg["email"]):
        print(f"notify: keychain item missing — create a Gmail app password, then:\n"
              f"  security add-generic-password -a {cfg['email']} -s {KEYCHAIN_SERVICE} -w \"$(pbpaste)\" -U")
        return 1
    ok = send_email(f"{SUBJECT_PREFIX} test email", "If you can read this, nightly reports will reach you.\n",
                    cfg["email"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
