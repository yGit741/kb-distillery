"""The contract every storage connector must meet, run against each implementation, plus the registry."""
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from kb import kbconfig
from kb.storage import (AuthStatus, Connector, NotFound, ObjectInfo, StorageError, connector_names, for_kb, load_class)
from kb.storage import registry
from kb.storage.localfolder import LocalFolder
from tests.storage.dummy_connector import MemoryStore

BAD_KEYS = ["", "/abs/x.pdf", "../escape.pdf", "raw/../x.pdf", "raw//x.pdf", "raw/./x.pdf", "raw\\x.pdf", "a\x00b"]


class ConnectorContract:
    """Mixed into one TestCase per implementation; `make()` returns a fresh, empty connector."""

    def make(self) -> Connector:
        raise NotImplementedError

    def setUp(self):
        self.c = self.make()

    def test_put_then_get_round_trips_bytes(self):
        self.c.put("raw/pdf/a.pdf", b"%PDF\x00\xff binary")
        self.assertEqual(self.c.get("raw/pdf/a.pdf"), b"%PDF\x00\xff binary")

    def test_an_existing_key_is_refused_unless_overwrite(self):
        self.c.put("raw/x.md", b"one")
        with self.assertRaises(StorageError):
            self.c.put("raw/x.md", b"two")
        self.assertEqual(self.c.get("raw/x.md"), b"one")                 # raw sources are immutable
        self.c.put("raw/x.md", b"two", overwrite=True)
        self.assertEqual(self.c.get("raw/x.md"), b"two")

    def test_list_is_sorted_and_filters_by_prefix(self):
        for key in ("raw/b/2.md", "raw/a/1.md", "raw/a/3.md", "meta/x.tsv"):
            self.c.put(key, b"x")
        self.assertEqual(list(self.c.list()), ["meta/x.tsv", "raw/a/1.md", "raw/a/3.md", "raw/b/2.md"])
        self.assertEqual(list(self.c.list("raw/a/")), ["raw/a/1.md", "raw/a/3.md"])
        self.assertEqual(list(self.c.list("raw/a/3")), ["raw/a/3.md"])
        self.assertEqual(list(self.c.list("nothing/")), [])

    def test_info_has_size_mtime_and_the_manifest_hash(self):
        data = b"hello raw source"
        self.c.put("raw/h.md", data)
        info = self.c.info("raw/h.md")
        self.assertIsInstance(info, ObjectInfo)
        self.assertEqual((info.key, info.size), ("raw/h.md", len(data)))
        self.assertEqual(info.sha1, hashlib.sha1(data).hexdigest())
        self.assertEqual(info.short, hashlib.sha1(data).hexdigest()[:12])       # what meta/corpus.tsv stores
        self.assertGreater(info.mtime_ns, 0)

    def test_a_missing_key_is_not_found_everywhere(self):
        for call in (self.c.get, self.c.info):
            with self.subTest(call=call.__name__), self.assertRaises(NotFound):
                call("raw/missing.md")
        with self.assertRaises(NotFound), self.c.local_copy("raw/missing.md"):
            pass
        self.assertFalse(self.c.exists("raw/missing.md"))

    def test_exists(self):
        self.c.put("raw/e.md", b"x")
        self.assertTrue(self.c.exists("raw/e.md"))

    def test_bad_keys_are_refused_by_every_method(self):
        for key in BAD_KEYS:
            with self.subTest(key=key):
                for call in (self.c.get, self.c.info, lambda k: self.c.put(k, b"x")):
                    with self.assertRaises(StorageError):
                        call(key)

    def test_local_copy_is_a_readable_file_with_the_same_bytes(self):
        self.c.put("raw/pdf/b.pdf", b"file bytes")
        with self.c.local_copy("raw/pdf/b.pdf") as path:
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith(".pdf"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"file bytes")

    def test_auth_reports_a_status(self):
        status = self.c.auth()
        self.assertIsInstance(status, AuthStatus)
        self.assertTrue(status.ok, status.message)


class LocalFolderContract(ConnectorContract, unittest.TestCase):
    def make(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return LocalFolder(self.tmp.name)

    def test_dotfiles_and_directories_are_not_listed(self):
        self.c.put("raw/a.md", b"x")
        with open(os.path.join(self.tmp.name, "raw", ".DS_Store"), "wb") as f:
            f.write(b"junk")
        os.makedirs(os.path.join(self.tmp.name, "raw", "empty-dir"))
        self.assertEqual(list(self.c.list()), ["raw/a.md"])

    def test_local_copy_is_the_file_itself_and_put_leaves_no_temp_files(self):
        self.c.put("raw/a.md", b"x")
        with self.c.local_copy("raw/a.md") as path:
            self.assertEqual(path, os.path.join(self.tmp.name, "raw", "a.md"))
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, "raw")), ["a.md"])

    def test_auth_fails_with_a_message_when_the_folder_is_gone(self):
        status = LocalFolder(os.path.join(self.tmp.name, "gone")).auth()
        self.assertFalse(status.ok)
        self.assertIn("gone", status.message)

    def test_it_takes_no_options(self):
        with self.assertRaises(StorageError):
            LocalFolder(self.tmp.name, token="x")


class MemoryStoreContract(ConnectorContract, unittest.TestCase):
    """A third-party-style connector passes the same suite."""

    def make(self):
        return MemoryStore("/unused")


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def kb(self, extra=""):
        root = os.path.join(self.tmp.name, "kbs", "x")
        os.makedirs(root)
        schema = "%d.%d" % kbconfig.SCHEMA_VERSION
        with open(os.path.join(root, "kb.toml"), "w") as f:
            f.write(f'[kb]\nid = "x"\nname = "X"\nschema_version = "{schema}"\n{extra}')
        return kbconfig.load_dir(root)

    def test_the_default_is_the_local_folder_at_the_kb_root(self):
        cfg = self.kb()
        c = for_kb(cfg)
        self.assertIsInstance(c, LocalFolder)
        self.assertEqual(c.root, cfg.root)

    def test_a_kb_can_name_a_connector_and_pass_options(self):
        fake = {"memory": "tests.storage.dummy_connector:MemoryStore"}
        with patch.object(registry, "_entry_points", return_value=fake):
            c = for_kb(self.kb('\n[storage]\nconnector = "memory"\n[storage.options]\nbucket = "b"\n'))
            self.assertIsInstance(c, MemoryStore)
            self.assertEqual(c.options, {"bucket": "b"})
            self.assertEqual(connector_names(), ["local-folder", "memory"])

    def test_a_package_cannot_replace_a_built_in(self):
        fake = {"local-folder": "tests.storage.dummy_connector:MemoryStore"}
        with patch.object(registry, "_entry_points", return_value=fake):
            self.assertIs(load_class("local-folder"), LocalFolder)

    def test_unknown_and_broken_connectors_say_what_is_wrong(self):
        with self.assertRaises(StorageError) as cm:
            load_class("nope")
        self.assertIn("local-folder", str(cm.exception))
        with patch.object(registry, "_entry_points", return_value={"bad": "no.such.module:X"}):
            with self.assertRaises(StorageError):
                load_class("bad")
        with patch.object(registry, "_entry_points", return_value={"notaconnector": "os.path:join"}):
            with self.assertRaises(StorageError) as cm:
                load_class("notaconnector")
            self.assertIn("Connector subclass", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
