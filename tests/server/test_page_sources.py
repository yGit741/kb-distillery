"""GET /api/pages/{slug}/sources on the fixture kb plus a few pages and corpus rows added for the test."""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import paths
from kb_distillery.server.app import create_app
from kb_distillery.server.models.page_sources import PageSources

PAPER = """---
type: paper
layer: source
raw: raw/printed-docs/2026-paper-x.pdf
created: 2026-10-01
---

# Paper X

Body.
"""
IDEA = """---
type: idea
layer: concept
sources: [{resource: ps-paper-x.md}, {resource: https://example.org/blog/post}]
---

# Soft claims

## Evidence

Shown in [Paper X](ps-paper-x.md) and at https://example.org/blog/post.

## Open questions

Nothing cited here.
"""
BARE = "---\ntype: idea\nlayer: concept\nsources: []\n---\n\n# Bare idea\n"
NOTE = """---
type: paper
layer: source
created: 2026-09-01
---

# Paper Y

Builds on [Paper X](ps-paper-x.md).
"""
LINKED = """---
type: idea
layer: concept
sources: []
---

# Linked idea

## Connections

- [Paper Y](ps-paper-y.md) states it; [Paper X](ps-paper-x.md) tests it, and [Paper Y](ps-paper-y.md) again.
- Related: [Soft claims](ps-soft-claims.md). `[Not a link](ps-bare.md)`

## My notes

My own pointer to [[ps-paper-z]] and [Paper Z](ps-paper-z.md).
"""
ROW = "raw/printed-docs/2026-paper-x.pdf\tabc123\tprinted-docs\tsource\tps-paper-x\t\t\n"


@pytest.fixture
def client():
    root = paths.ROOT
    made = {f"wiki/{n}.md": t for n, t in (("ps-paper-x", PAPER), ("ps-soft-claims", IDEA), ("ps-bare", BARE),
                                                ("ps-paper-y", NOTE), ("ps-paper-z", NOTE.replace("Paper Y", "Paper Z")),
                                                ("ps-linked", LINKED))}
    corpus = os.path.join(root, "meta", "corpus.tsv")
    old = open(corpus, encoding="utf-8").read() if os.path.exists(corpus) else None
    os.makedirs(os.path.dirname(corpus), exist_ok=True)
    for rel, text in made.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(text)
    with open(corpus, "w", encoding="utf-8") as f:
        f.write((old or "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n") + ROW)
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        for rel in made:
            os.remove(os.path.join(root, rel))
        if old is None:
            os.remove(corpus)
        else:
            with open(corpus, "w", encoding="utf-8") as f:
                f.write(old)


def test_concept_page_lists_source_page_raw_file_and_url(client):
    r = client.get("/api/pages/ps-soft-claims/sources")
    assert r.status_code == 200
    body = PageSources.model_validate(r.json())
    assert body.slug == "ps-soft-claims" and body.counts.total == 2
    by = {s.id: s for s in body.sources}
    raw = by["raw/printed-docs/2026-paper-x.pdf"]
    assert (raw.title, raw.kind, raw.format, raw.disposition) == ("Paper X", "pdf", "printed-docs", "source")
    assert raw.slug == "ps-paper-x" and raw.added == "2026-10-01" and raw.via == ["sources", "links"]
    assert raw.route == "/pipeline?q=raw/printed-docs/2026-paper-x.pdf"
    assert raw.cited_in_sections == ["Evidence"]
    web = by["https://example.org/blog/post"]
    assert web.disposition == "external" and web.kind == "web" and web.cited_in_sections == ["Evidence"]
    assert body.counts.raw == 1 and body.counts.external == 1 and body.counts.by_disposition == {"source": 1, "external": 1}


def test_concept_page_counts_source_pages_linked_in_its_text(client):
    body = PageSources.model_validate(client.get("/api/pages/ps-linked/sources").json())
    # reading order, once each; the concept page, the code span and `## My notes` do not count
    assert [s.id for s in body.sources] == ["ps-paper-y", "raw/printed-docs/2026-paper-x.pdf"]
    page, raw = body.sources
    assert (page.format, page.disposition, page.slug, page.route, page.via) == ("page", "page", "ps-paper-y", "/pages/ps-paper-y", ["links"])
    assert page.cited_in_sections == ["Connections"] and page.added == "2026-09-01"
    assert (raw.title, raw.slug, raw.via, raw.cited_in_sections) == ("Paper X", "ps-paper-x", ["links"], ["Connections"])
    assert body.counts.total == 2 and body.counts.raw == 1 and body.counts.pages == 1


def test_declared_source_that_is_also_linked_is_listed_once(client):
    body = client.get("/api/pages/ps-soft-claims/sources").json()
    raw = [s for s in body["sources"] if s["slug"] == "ps-paper-x"]
    assert len(raw) == 1 and raw[0]["via"] == ["sources", "links"]


def test_source_page_does_not_count_the_sources_it_links(client):
    body = client.get("/api/pages/ps-paper-y/sources").json()
    assert body["sources"] == []


def test_source_page_lists_its_own_raw_file(client):
    body = client.get("/api/pages/ps-paper-x/sources").json()
    assert [s["path_rel"] for s in body["sources"]] == ["raw/printed-docs/2026-paper-x.pdf"]
    assert body["sources"][0]["via"] == ["raw"]


def test_page_without_sources_is_empty_not_404(client):
    r = client.get("/api/pages/ps-bare/sources")
    assert r.status_code == 200
    assert r.json()["sources"] == [] and r.json()["counts"]["total"] == 0


def test_unknown_slug_and_unknown_kb_are_404(client):
    assert client.get("/api/pages/no-such-page-xyz/sources").status_code == 404
    assert client.get("/api/pages/ps-bare/sources", params={"kb": "nope"}).status_code == 404
