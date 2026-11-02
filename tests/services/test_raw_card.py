"""Home pipeline raw cards: one per format, the privacy column, the share bake budget, and the API route."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.corpus import RawCard
from kb_distillery.services import corpus
from kb_distillery.services.raw_card import bake_cards, public_card, raw_card
from kb_distillery.publish.site.build import raw_paths_of

CHAT = """---
source: https://gemini.google.com/app/abc
title: "Boolean chat"
---
**You**

what is XOR

---

**Gemini**

The same as symmetric difference.

---

**You**

thanks
"""
CLIP = """---
title: "Brush Up"
blog: "gilkalai.wordpress.com"
url: https://gilkalai.wordpress.com/2008/06/02/x/
source: wordpress.com REST API v1.1
---
# Brush Up

Original: https://gilkalai.wordpress.com/2008/06/02/x/

A short post about posets.
"""


@pytest.fixture
def vault(tmp_path):
    for fmt in ("printed-docs", "llm-chats", "web-clips", "emails/t1"):
        (tmp_path / "raw" / fmt).mkdir(parents=True)
    from tests import pdfkit
    doc = pdfkit.Doc()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "Why are sensitive functions hard?")
    doc.save(tmp_path / "raw" / "printed-docs" / "2024-x.pdf")
    (tmp_path / "raw" / "llm-chats" / "c.md").write_text(CHAT)
    (tmp_path / "raw" / "web-clips" / "w.md").write_text(CLIP)
    (tmp_path / "raw" / "web-clips" / "yt.md").write_text("---\ntitle: Talk\nsource: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n---\nA talk.\n")
    (tmp_path / "raw" / "emails" / "t1" / "thread.md").write_text("---\nsubject: Hi\nparticipants: [a@x.org, b@y.org]\ndate-range: 2021-01-02..2021-01-03\n---\n# Hi\n\nbody text\n")
    return tmp_path


def card(root, rel):
    return raw_card(str(root / rel), rel, str(root), with_added=False)


def test_pdf_card_has_pages_size_and_a_thumb(vault):
    c = card(vault, "raw/printed-docs/2024-x.pdf")
    assert c["kind"] == "pdf" and c["facts"]["pages"] == 3 and c["facts"]["bytes"] > 0 and c["has_thumb"]
    RawCard.model_validate(c)


def test_chat_web_youtube_email_cards(vault):
    chat = card(vault, "raw/llm-chats/c.md")
    assert chat["kind"] == "chat" and chat["model"] == "Gemini" and chat["turn_count"] == 3
    assert [t["role"] for t in chat["turns"]] == ["user", "model", "user"] and chat["turns"][0]["text"] == "what is XOR"
    web = card(vault, "raw/web-clips/w.md")
    assert web["kind"] == "web" and web["url"].startswith("https://gilkalai") and web["site"] == "gilkalai.wordpress.com"
    assert "Original:" not in web["excerpt"] and "posets" in web["excerpt"]
    yt = card(vault, "raw/web-clips/yt.md")
    assert yt["kind"] == "youtube" and yt["video_id"] == "dQw4w9WgXcQ"
    mail = card(vault, "raw/emails/t1/thread.md")
    assert mail["kind"] == "email" and mail["header"]["subject"] == "Hi" and "a@x.org" in mail["header"]["sender"]
    for c in (chat, web, yt, mail):
        RawCard.model_validate(c)


def test_public_card_is_the_privacy_column(vault):
    chat = public_card(card(vault, "raw/llm-chats/c.md"))
    assert chat["turns"] == [] and chat["title"] is None and chat["path"] is None and chat["name"] is None
    assert chat["facts"]["bytes"] and chat["model"] == "Gemini"
    web = public_card(card(vault, "raw/web-clips/w.md"))
    assert web["excerpt"] and web["path"] is None and web["name"] is None
    clipped = public_card(dict(card(vault, "raw/web-clips/w.md"), url="https://chatgpt.com/share/x"))
    assert clipped["excerpt"] is None and clipped["url"] is None


def test_bake_budget_thumbs_best_read_first_and_no_raw_path_in_public(vault):
    nodes = [
        {"id": "s-easy", "layer": "source", "depth": "easy", "properties": {"raw": "raw/printed-docs/2024-x.pdf"}},
        {"id": "s-deep", "layer": "source", "depth": "deep", "properties": {"raw": "raw/printed-docs/2024-x.pdf, raw/x.md"}},
        {"id": "s-chat", "layer": "source", "depth": "full", "properties": {"raw": "raw/llm-chats/c.md"}},
        {"id": "s-gone", "layer": "source", "depth": "full", "properties": {"raw": "raw/inbox/y.pdf"}},
        {"id": "idea", "layer": "concept", "properties": {}},
    ]
    raw_of = raw_paths_of(nodes)
    assert raw_of["s-deep"] == "raw/printed-docs/2024-x.pdf" and "idea" not in raw_of
    one = len(bake_cards(nodes[1:2], raw_of, str(vault))["s-deep"]["thumb"])
    cards = bake_cards(nodes, raw_of, str(vault), public=True, thumb_budget=one)
    assert set(cards) == {"s-easy", "s-deep", "s-chat"}                       # never raw/inbox
    assert cards["s-deep"]["thumb"].startswith("data:image/jpeg;base64,") and len(cards["s-deep"]["thumb"]) <= 60_000
    assert cards["s-easy"]["thumb"] is None and not cards["s-easy"]["has_thumb"]   # budget spent on the deep one
    assert "raw/" not in json.dumps(cards) and "2024-x" not in json.dumps(cards)


def test_card_route(vault):
    with mock.patch.object(corpus, "ROOT", str(vault)), TestClient(create_app()) as c:
        r = c.get("/api/raw/raw/printed-docs/2024-x.pdf/card")
        assert r.status_code == 200 and RawCard.model_validate(r.json()).facts.pages == 3
        assert c.get("/api/raw/raw/printed-docs/missing.pdf/card").status_code == 404


def test_blockquote_original_line_is_stripped(vault):
    (vault / "raw" / "web-clips" / "q.md").write_text("---\ntitle: Q\n---\n# Q\n\n> Original: https://gilkalai.wordpress.com/2008/04/29/hello-world/ · 2008-04-29\n\nHello world post.\n")
    web = card(vault, "raw/web-clips/q.md")
    assert "Original" not in web["excerpt"] and "gilkalai" not in web["excerpt"] and "Hello world" in web["excerpt"]


def test_public_handwritten_and_images_get_facts_only(vault):
    from tests import pdfkit
    (vault / "raw" / "handwritten").mkdir()
    doc = pdfkit.Doc()
    doc.new_page().insert_text((72, 72), "my notes")
    doc.save(vault / "raw" / "handwritten" / "n.pdf")
    rel = "raw/handwritten/n.pdf"
    private = card(vault, rel)
    assert private["kind"] == "handwritten" and private["has_thumb"]
    pub = public_card(dict(private, thumb="data:image/jpeg;base64,xx"))
    assert pub["thumb"] is None and not pub["has_thumb"] and pub["facts"]["pages"] == 1
    assert public_card({"kind": "image", "facts": {}, "has_thumb": True, "thumb": "x"})["thumb"] is None
    nodes = [{"id": "s-hw", "layer": "source", "depth": "deep", "properties": {"raw": rel}}]
    raw_of = raw_paths_of(nodes)
    assert bake_cards(nodes, raw_of, str(vault))["s-hw"]["thumb"]                    # private build keeps page 1
    baked = bake_cards(nodes, raw_of, str(vault), public=True)["s-hw"]
    assert baked["thumb"] is None and not baked["has_thumb"] and baked["facts"]["pages"] == 1
