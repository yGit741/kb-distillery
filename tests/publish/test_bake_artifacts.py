"""What a share build bakes of the artifact layer: the graph as the builder wrote it, and the cites of the pages the
site carries only. Fakes only: the fixture kb copied to a temp folder, no network, no model."""
import shutil
from pathlib import Path

import pytest

from kb_distillery.publish.site import build

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "artifacts" / "kb-code"


@pytest.fixture
def kb(tmp_path):
    root = tmp_path / "kb-code"
    shutil.copytree(FIXTURE, root)
    return root


def test_bakes_the_layer_with_the_cites_of_the_carried_pages_only(kb):
    out = build.bake_artifacts({"pages": {"buffer-copy": {}, "other": {}}}, str(kb))
    art = out["artifacts"]
    assert len(art["nodes"]) == 4 and art["views"][0]["id"] == "dependencies"
    assert art["cites"] == {"buffer-copy": ["F0a1b2", "F3c4d5"]}


def test_a_build_without_pages_keeps_no_cites(kb):
    assert build.bake_artifacts({}, str(kb))["artifacts"]["cites"] == {}


def test_a_kb_without_a_layer_bakes_nothing(kb):
    (kb / "artifacts" / "graph.json").unlink()
    assert build.bake_artifacts({"pages": {"buffer-copy": {}}}, str(kb)) == {}
