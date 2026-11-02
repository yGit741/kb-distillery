"""Export archive names come from the kb id: the id `jane-research` gives `jane-research-kb-<stamp>.zip`."""
import os
from types import SimpleNamespace
from unittest import mock

from kb_distillery.config import paths
from kb_distillery.publish import export


def test_prefix_is_the_kb_id_plus_kb():
    with mock.patch.object(paths, "KB", SimpleNamespace(id="jane-research")):
        assert export.prefix() == "jane-research-kb"
        assert export._archive_name("2026-01-01T000000Z") == "jane-research-kb-2026-01-01T000000Z.zip"


def test_prefix_without_a_selected_kb_uses_the_vault_folder_name():
    with mock.patch.object(paths, "KB", None), mock.patch.object(export, "ROOT", os.path.join(os.sep, "x", "notes")):
        assert export.prefix() == "notes-kb"


def test_list_exports_matches_only_this_kbs_archives(tmp_path):
    for name in ("demo-kb-a.zip", "other-kb-a.zip", "demo-kb-a.txt"):
        (tmp_path / name).write_text("x")
    with mock.patch.object(paths, "KB", SimpleNamespace(id="demo")), mock.patch.object(export, "EXPORT_DIR", str(tmp_path)):
        assert export.list_exports() == ["demo-kb-a.zip"]


def test_manifest_title_names_the_kb_not_a_person():
    with mock.patch.object(paths, "KB", SimpleNamespace(id="jane-research", name="Jane Research")):
        first = export._manifest(["wiki/a.md"], False, "2026-01-01T000000Z").splitlines()[0]
    assert first == "Jane Research export"
