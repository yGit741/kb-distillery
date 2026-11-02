"""The contract every publisher must meet, run against each implementation, plus the registry.

A publisher in its own package subclasses `PublisherContract` (or copies it) with a `make()` that returns a publisher
wired to fakes: no test here may reach a real site, account or tool."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery import kbconfig
from kb_distillery.publish import (NotConfigured, NotSupported, NullPublisher, PublishError, PublishResult, Publisher, Snapshot,
                        current, for_kb, load_class, publisher_names, selected_name)
from kb_distillery.hosting import registry
from kb_distillery.hosting.base import STATUS_KEYS
from tests.publish.fake_publisher import MemoryPublisher

FAKE = {"memory": "tests.publish.fake_publisher:MemoryPublisher"}


class PublisherContract:
    """Mixed into one TestCase per implementation; `make()` returns a publisher that touches nothing real."""

    def make(self) -> Publisher:
        raise NotImplementedError

    def setUp(self):
        self.p = self.make()

    def test_it_has_a_name_and_is_a_publisher(self):
        self.assertIsInstance(self.p, Publisher)
        self.assertTrue(self.p.name)

    def test_available_is_a_bool_and_never_raises(self):
        self.assertIsInstance(self.p.available(), bool)

    def test_status_is_none_or_a_dict_of_the_status_keys(self):
        status = self.p.status()
        if status is not None:
            self.assertEqual(set(status), set(STATUS_KEYS))

    def test_log_tail_is_text(self):
        self.assertIsInstance(self.p.log_tail(5), str)

    def test_request_publish_returns_a_word_and_does_not_raise(self):
        self.assertIsInstance(self.p.request_publish("test"), str)

    def test_optional_reads_have_empty_defaults(self):
        self.assertIsInstance(self.p.snapshots(), list)
        self.assertIsInstance(self.p.orphan_snapshots(), list)


class NullContract(PublisherContract, unittest.TestCase):
    def make(self):
        return NullPublisher()

    def test_it_is_unavailable_and_publishes_nothing(self):
        self.assertFalse(self.p.available())
        self.assertIsNone(self.p.status())
        with self.assertRaises(NotConfigured) as cm:
            self.p.publish(Snapshot("main"))
        self.assertIn("no publisher configured", str(cm.exception))

    def test_the_reason_is_kept(self):
        self.assertEqual(NullPublisher(reason="because").reason, "because")

    def test_optional_operations_are_not_supported(self):
        for call in (self.p.rollback, lambda: self.p.audit("main"), self.p.account_api):
            with self.assertRaises(NotSupported):
                call()


class MemoryContract(PublisherContract, unittest.TestCase):
    """A third-party-style publisher passes the same suite."""

    def make(self):
        return MemoryPublisher("/unused")

    def test_publish_then_status(self):
        self.assertIsNone(self.p.status())
        res = self.p.publish(Snapshot("main"))
        self.assertIsInstance(res, PublishResult)
        self.assertEqual(self.p.status()["state"], "deployed")

    def test_dry_run_publishes_nothing(self):
        self.p.publish(Snapshot("main"), dry_run=True)
        self.assertIsNone(self.p.status())


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(registry.ENV, None)
        os.environ[registry.ENGINE_CONFIG_ENV] = os.path.join(self.tmp.name, "no-engine.toml")

    def kb(self, extra=""):
        root = os.path.join(self.tmp.name, "kbs", "x")
        os.makedirs(root, exist_ok=True)
        schema = "%d.%d" % kbconfig.SCHEMA_VERSION
        with open(os.path.join(root, "kb.toml"), "w") as f:
            f.write(f'[kb]\nid = "x"\nname = "X"\nschema_version = "{schema}"\n{extra}')
        return kbconfig.load_dir(root)

    def test_no_publisher_configured_is_the_null_publisher(self):
        cfg = self.kb()
        p = for_kb(cfg)
        self.assertIsInstance(p, NullPublisher)
        self.assertEqual(p.root, cfg.root)
        self.assertEqual(selected_name(cfg), "")

    def test_a_kb_can_name_a_publisher_and_pass_options(self):
        with patch.object(registry, "_entry_points", return_value=FAKE):
            p = for_kb(self.kb('\n[publish]\npublisher = "memory"\n[publish.options]\nbucket = "b"\n'))
            self.assertIsInstance(p, MemoryPublisher)
            self.assertEqual(p.options, {"bucket": "b"})
            self.assertEqual(publisher_names(), ["cloudflare", "memory"])

    def test_the_engine_default_comes_from_the_environment_and_the_kb_wins(self):
        os.environ[registry.ENV] = "memory"
        with patch.object(registry, "_entry_points", return_value=FAKE):
            self.assertIsInstance(for_kb(self.kb()), MemoryPublisher)
            self.assertIsInstance(for_kb(self.kb('\n[publish]\npublisher = "none"\n')), NullPublisher)

    def test_the_engine_config_is_the_last_default_and_everything_above_it_wins(self):
        engine = os.path.join(self.tmp.name, "engine.toml")
        with open(engine, "w") as f:
            f.write('[publish]\npublisher = "memory"\n')
        os.environ[registry.ENGINE_CONFIG_ENV] = engine
        with patch.object(registry, "_entry_points", return_value=FAKE):
            self.assertIsInstance(for_kb(self.kb()), MemoryPublisher)
            os.environ[registry.ENV] = "none"                              # the environment beats the engine file
            self.assertIsInstance(for_kb(self.kb()), NullPublisher)
            del os.environ[registry.ENV]
            self.assertIsInstance(for_kb(self.kb('\n[publish]\npublisher = "none"\n')), NullPublisher)   # so does the kb

    def test_a_missing_or_broken_engine_config_means_none(self):
        os.environ[registry.ENGINE_CONFIG_ENV] = os.path.join(self.tmp.name, "gone.toml")
        self.assertEqual(selected_name(self.kb()), "")
        bad = os.path.join(self.tmp.name, "bad.toml")
        with open(bad, "w") as f:
            f.write("[publish\n")
        os.environ[registry.ENGINE_CONFIG_ENV] = bad
        self.assertEqual(selected_name(self.kb()), "")

    def test_a_package_cannot_replace_a_built_in(self):
        built = {"fixed": "tests.publish.fake_publisher:MemoryPublisher"}
        with patch.object(registry, "BUILTIN", built), \
                patch.object(registry, "_entry_points", return_value={"fixed": "os.path:join"}):
            self.assertIs(load_class("fixed"), MemoryPublisher)

    def test_none_cannot_be_registered_by_a_package(self):
        with patch.object(registry, "_entry_points", return_value={"none": "tests.publish.fake_publisher:MemoryPublisher"}):
            self.assertEqual(publisher_names(), ["cloudflare"])

    def test_unknown_and_broken_publishers_say_what_is_wrong(self):
        with self.assertRaises(PublishError):
            load_class("nope")
        with patch.object(registry, "_entry_points", return_value={"bad": "no.such.module:X"}):
            with self.assertRaises(PublishError):
                load_class("bad")
        with patch.object(registry, "_entry_points", return_value={"notapub": "os.path:join"}):
            with self.assertRaises(PublishError) as cm:
                load_class("notapub")
            self.assertIn("Publisher subclass", str(cm.exception))

    def test_current_never_raises_and_says_why(self):
        p = current(self.kb('\n[publish]\npublisher = "nope"\n'))
        self.assertIsInstance(p, NullPublisher)
        self.assertIn("nope", p.reason)

    def test_importing_the_interface_does_not_import_a_publisher(self):
        import subprocess
        code = "import sys, kb_distillery.publish; sys.exit(1 if any(m == 'kb_distillery.publish.cloudflare' or m.startswith('kb_distillery.publish.cloudflare.') for m in sys.modules) else 0)"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
