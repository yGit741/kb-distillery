#!/usr/bin/env python3
"""Tests for src/kb_distillery/ops/notify.py — the nightly email: when it is sent, what it says, how it fails."""
import datetime
import json
import os
import smtplib
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.ops import notify
from kb_distillery.ops import hygiene

NOW = datetime.datetime(2026, 10, 22, 22, 0, tzinfo=datetime.timezone.utc)
CFG = {"email": "me@example.com", "on": ["error", "warn"], "min_interval_hours": 20}


def report(*findings):
    return hygiene.Report(findings=list(findings), checks=["x"], started=NOW.isoformat())


ERR = hygiene.Finding("error", "unpushed-steps", "main is 1 commit(s) ahead of origin/main", "pixi run daily-sync")
WARN = hygiene.Finding("warn", "stale-worktree", "infra/x merged", "pixi run ship -- prune --apply")


class FakeSMTP:
    """Records login + sent message; raised errors come from `fail`."""
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.login_args, self.sent = host, port, None, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


class SendEmail(unittest.TestCase):
    def setUp(self):
        FakeSMTP.instances.clear()

    def test_sends_over_gmail_ssl_as_the_recipient(self):
        ok = notify.send_email("[thesis-kb] s", "body\n", "me@example.com", password="app-pw", smtp_cls=FakeSMTP)
        self.assertTrue(ok)
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port), ("smtp.gmail.com", 465))
        self.assertEqual(smtp.login_args, ("me@example.com", "app-pw"))
        msg = smtp.sent[0]
        self.assertEqual((msg["From"], msg["To"], msg["Subject"]), ("me@example.com", "me@example.com", "[thesis-kb] s"))
        self.assertEqual(msg.get_content(), "body\n")

    def test_missing_keychain_item_returns_false_without_raising(self):
        with patch.object(notify, "keychain_password", return_value=None):
            self.assertFalse(notify.send_email("s", "b", "me@example.com", smtp_cls=FakeSMTP))
        self.assertEqual(FakeSMTP.instances, [])

    def test_no_recipient_returns_false(self):
        self.assertFalse(notify.send_email("s", "b", "", password="x", smtp_cls=FakeSMTP))

    def test_smtp_failure_returns_false(self):
        class Refusing(FakeSMTP):
            def login(self, user, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        self.assertFalse(notify.send_email("s", "b", "me@example.com", password="x", smtp_cls=Refusing))

    def test_keychain_password_uses_security_and_hides_failure(self):
        class P:
            def __init__(self, rc, out):
                self.returncode, self.stdout = rc, out
        with patch.object(notify.subprocess, "run", return_value=P(0, "secret\n")) as run:
            self.assertEqual(notify.keychain_password("me@example.com"), "secret")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:2], ["security", "find-generic-password"])
        self.assertIn("kb-distillery-gmail", cmd)
        with patch.object(notify.subprocess, "run", return_value=P(44, "")):
            self.assertIsNone(notify.keychain_password("me@example.com"))
        with patch.object(notify.subprocess, "run", side_effect=OSError("no security binary")):
            self.assertIsNone(notify.keychain_password("me@example.com"))


class NotifyReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, subject, body, to):
        self.sent.append((subject, body, to))
        return True

    def test_clean_report_sends_nothing(self):
        self.assertEqual(notify.notify_report(report(), self.root, cfg=CFG, now=NOW, send=self.send), "clean")
        self.assertEqual(self.sent, [])

    def test_findings_send_once_then_throttle_then_resend_after_interval(self):
        r = report(ERR, WARN)
        self.assertEqual(notify.notify_report(r, self.root, cfg=CFG, now=NOW, send=self.send), "sent")
        subject, body, to = self.sent[0]
        self.assertEqual(to, "me@example.com")
        self.assertEqual(subject, "[thesis-kb] nightly: 2 problems (unpushed-steps, stale-worktree)")
        self.assertIn("[ERROR] unpushed-steps", body)
        self.assertIn("fix: pixi run daily-sync", body)
        self.assertNotIn("daily-sync log", body)
        with open(os.path.join(self.root, "meta", ".ops", "notify-last.json")) as f:
            self.assertEqual(json.load(f)["fingerprint"], r.fingerprint())
        later = NOW + datetime.timedelta(hours=5)
        self.assertEqual(notify.notify_report(r, self.root, cfg=CFG, now=later, send=self.send), "throttled")
        self.assertEqual(len(self.sent), 1)
        much_later = NOW + datetime.timedelta(hours=21)
        self.assertEqual(notify.notify_report(r, self.root, cfg=CFG, now=much_later, send=self.send), "sent")
        self.assertEqual(len(self.sent), 2)

    def test_a_different_report_is_sent_right_away(self):
        notify.notify_report(report(ERR), self.root, cfg=CFG, now=NOW, send=self.send)
        status = notify.notify_report(report(ERR, WARN), self.root, cfg=CFG, now=NOW + datetime.timedelta(hours=1),
                                      send=self.send)
        self.assertEqual(status, "sent")
        self.assertEqual(len(self.sent), 2)

    def test_severity_filter(self):
        only_errors = dict(CFG, on=["error"])
        self.assertEqual(notify.notify_report(report(WARN), self.root, cfg=only_errors, now=NOW, send=self.send), "clean")
        self.assertEqual(notify.notify_report(report(ERR), self.root, cfg=only_errors, now=NOW, send=self.send), "sent")

    def test_sync_failure_is_sent_even_when_hygiene_is_clean(self):
        status = notify.notify_report(report(), self.root, sync_failed=True, error="Traceback …\nRuntimeError: push exploded",
                                      tail="=== Thu\npushed\nerror\n", cfg=CFG, now=NOW, send=self.send)
        self.assertEqual(status, "sent")
        subject, body, _ = self.sent[0]
        self.assertEqual(subject, "[thesis-kb] nightly sync FAILED")
        self.assertIn("RuntimeError: push exploded", body)
        self.assertIn("--- daily-sync log (last lines) ---\n=== Thu\npushed\nerror", body)

    def test_failed_send_is_not_remembered(self):
        status = notify.notify_report(report(ERR), self.root, cfg=CFG, now=NOW, send=lambda *a: False)
        self.assertEqual(status, "not-sent")
        self.assertFalse(os.path.exists(os.path.join(self.root, "meta", ".ops", "notify-last.json")))
        self.assertEqual(notify.notify_report(report(ERR), self.root, cfg=CFG, now=NOW, send=self.send), "sent")

    def test_missing_keychain_in_the_real_sender_never_raises(self):
        with patch.object(notify, "keychain_password", return_value=None):
            self.assertEqual(notify.notify_report(report(ERR), self.root, cfg=CFG, now=NOW), "not-sent")


class DigestMail(unittest.TestCase):
    """mode = "digest": the nightly report Doc goes out every night as HTML + text."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, subject, body, to, html=None):
        self.sent.append((subject, body, to, html))
        return True

    def doc(self, r):
        from kb_distillery.ops import nightly_report
        return nightly_report.build(ROOT, r, [], now=NOW, version="kb-0.1.2", site={}, vault={}, steps=[])

    def test_clean_night_is_mailed_in_digest_mode(self):
        r = report()
        status = notify.notify_report(r, self.root, cfg=dict(CFG, mode="digest"), now=NOW, send=self.send, doc=self.doc(r))
        self.assertEqual(status, "sent")
        subject, body, _to, html = self.sent[0]
        self.assertEqual(subject, "[thesis-kb] ✓ all clear · 0 open threads")
        self.assertIn("All clear", body)
        self.assertTrue(html.startswith("<!doctype html>"))
        later = NOW + datetime.timedelta(hours=3)            # same report → throttled within the interval
        self.assertEqual(notify.notify_report(r, self.root, cfg=dict(CFG, mode="digest"), now=later, send=self.send,
                                              doc=self.doc(r)), "throttled")

    def test_problems_mode_keeps_clean_nights_quiet(self):
        r = report()
        self.assertEqual(notify.notify_report(r, self.root, cfg=dict(CFG, mode="problems"), now=NOW, send=self.send,
                                              doc=self.doc(r)), "clean")

    def test_findings_use_the_report_subject(self):
        r = report(ERR, WARN)
        notify.notify_report(r, self.root, cfg=dict(CFG, mode="digest"), now=NOW, send=self.send, doc=self.doc(r))
        self.assertEqual(self.sent[0][0], "[thesis-kb] ✗ 1 thing needs you · unpushed-steps, stale-worktree")

    def test_send_email_attaches_the_html_alternative(self):
        FakeSMTP.instances.clear()
        ok = notify.send_email("s", "plain\n", "me@example.com", password="x", smtp_cls=FakeSMTP, html="<p>hi</p>")
        self.assertTrue(ok)
        msg = FakeSMTP.instances[0].sent[0]
        self.assertTrue(msg.is_multipart())
        self.assertEqual([p.get_content_type() for p in msg.iter_parts()], ["text/plain", "text/html"])


class Config(unittest.TestCase):
    def test_committed_config(self):
        cfg = notify.load_config(ROOT)
        self.assertEqual(cfg["email"], "ygreenshpan@gmail.com")
        self.assertEqual(cfg["mode"], "digest")
        self.assertEqual(cfg["on"], ["error", "warn"])
        self.assertEqual(cfg["min_interval_hours"], 20)

    def test_missing_config_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = notify.load_config(tmp)
        self.assertEqual(cfg["email"], "")
        self.assertEqual(cfg["on"], ["error", "warn"])

    def test_log_tail(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("".join(f"line {i}\n" for i in range(50)))
        try:
            tail = notify.log_tail(f.name, n=30)
        finally:
            os.unlink(f.name)
        self.assertEqual(tail.splitlines()[0], "line 20")
        self.assertEqual(len(tail.splitlines()), 30)
        self.assertEqual(notify.log_tail("/nonexistent/log"), "")

    def test_keychain_falls_back_to_the_old_service_name_read_only(self):
        class P:
            def __init__(self, rc, out):
                self.returncode, self.stdout = rc, out
        seen = []

        def fake(cmd, **kw):
            seen.append(cmd[cmd.index("-s") + 1])
            return P(0, "old-secret\n") if cmd[cmd.index("-s") + 1] == "thesis-kb-gmail" else P(44, "")
        with patch.object(notify.subprocess, "run", side_effect=fake):
            self.assertEqual(notify.keychain_password("me@example.com"), "old-secret")
        self.assertEqual(seen, ["kb-distillery-gmail", "thesis-kb-gmail"])

    def test_cli_test_without_keychain_item_explains(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with patch.object(notify, "keychain_password", return_value=None), redirect_stdout(buf):
            rc = notify.main(["--test"])
        self.assertEqual(rc, 1)
        self.assertIn("security add-generic-password -a ygreenshpan@gmail.com -s kb-distillery-gmail", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
