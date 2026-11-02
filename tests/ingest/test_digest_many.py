"""digest-many: frontmatter merge when a page is deepened in place, shared reply validation, batch submit/collect/drive."""
import json
from types import SimpleNamespace

import pytest

from kb_distillery import llm
from kb_distillery.ingest import digest_many, extract
from kb_distillery.ingest.fm_merge import merge_frontmatter

OLD = """---
type: blog-post
blog: "Combinatorics and More"
layer: source
author: Gil Kalai
area: []
maturity: digested
depth: easy
raw: raw/web-clips/k-1.md
url: https://example.org/a/
created: 2009-04-25T00:00:00Z
related: [gil-kalai.md, series-gil-kalai-blog.md]
title: "A Problem"
description: "Kozma's conjecture."
---

# A Problem

## My notes

mine
"""
NEW = """---
type: blog-post
layer: source
series: series-gil-kalai-blog
authors: []
year:
area: [boolean-analysis]
maturity: digested
depth: full
raw: raw/web-clips/k-1.md
citekey:
url:
recommended_by: []
discussed_with: []
related: [series-gil-kalai-blog.md, total-influence.md]
---

# A Problem

**Problem:** p
"""


def fields(text):
    head = text.split("\n---\n", 1)[0]
    return dict(line.split(": ", 1) for line in head.splitlines()[1:] if ": " in line)


def test_merge_keeps_what_the_page_says_and_takes_depth_and_area():
    out = merge_frontmatter(OLD, NEW)
    f = fields(out)
    assert f["depth"] == "full" and f["area"] == "[boolean-analysis]"      # an empty field takes the draft's
    assert f["blog"] == '"Combinatorics and More"' and f["author"] == "Gil Kalai"
    assert f["created"] == "2009-04-25T00:00:00Z" and f["url"] == "https://example.org/a/" and f["description"] == '"Kozma\'s conjecture."'
    assert f["related"] == "[gil-kalai.md, series-gil-kalai-blog.md, total-influence.md]"     # union, order kept
    assert "series" not in f and "authors" not in f and "citekey" not in f         # nothing empty or hub-keyed is added
    assert out.endswith("**Problem:** p\n") and "# A Problem" in out              # the body is the draft's


def test_merge_never_overwrites_a_filled_area_and_adds_missing_filled_fields():
    old = OLD.replace("area: []", "area: [quantum]")
    new = NEW.replace("year:\n", "year: 2009\n")
    f = fields(merge_frontmatter(old, new))
    assert f["area"] == "[quantum]" and f["year"] == "2009"


def test_merge_without_existing_frontmatter_returns_the_draft():
    assert merge_frontmatter("no frontmatter", NEW) == NEW


RAW = "raw/web-clips/k-1.md"
GOOD = {"raw": RAW, "title": "T", "problem": "p", "method": "m", "results": ["r"], "equations": [{"latex": "x", "variables": {}, "label": ""}],
        "concepts": ["c"], "open_questions": [], "citekey": "", "url": "", "year": 2009, "authors": []}


def result(text, error=""):
    return llm.Result(id="x", text=text, error=error, usd=0.01, backend="batch", model="claude-sonnet-5-5")


def test_claims_from_result_locks_session_fields_and_explains_rejections():
    claims, why = extract.claims_from_result(result("sure\n" + json.dumps({**GOOD, "raw": "other"})), {"raw": RAW})
    assert why is None and claims["raw"] == RAW
    draft, why = extract.claims_from_result(result("no json here"), {"raw": RAW})
    assert draft == {"reply": "no json here"} and "no JSON" in why
    draft, why = extract.claims_from_result(result(json.dumps(GOOD), error="cut at max_tokens"), {"raw": RAW})
    assert "cut at max_tokens" in why and draft["title"] == "T"


@pytest.fixture
def vault(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    for n, topic, tier in ((1, "comb", "★"), (2, "comb", "★★★"), (3, "tyi", "★★★"), (4, "comb", "★★")):
        (tmp_path / "raw" / "web-clips").mkdir(parents=True, exist_ok=True)
        (tmp_path / "raw" / "web-clips" / f"k-{n}.md").write_text(f"# Post {n}\n\nbody {n}\n")
        (wiki / f"blog-k-{n}.md").write_text(
            f"---\ntype: blog-post\ndepth: {'full' if n == 4 else 'easy'}\nraw: raw/web-clips/k-{n}.md\n"
            f"url: https://example.org/{n}/\n---\n# P{n}\n")
    rows = "".join(f"| 2009-0{n}-01 | [P{n}](https://example.org/{n}/) | `{t}` | {r} | Cat |\n"
                   for n, t, r in ((1, "comb", "★"), (2, "comb", "★★★"), (3, "tyi", "★★★"), (4, "comb", "★★")))
    (wiki / "series-k.md").write_text("---\ntype: series\n---\n# K\n\n## Posts by year\n\n### 2009\n\n"
                                      "| Date | Post | Topic | Rel. | Categories |\n|---|---|---|---|---|\n" + rows)
    monkeypatch.setattr(digest_many, "ROOT", str(tmp_path))
    monkeypatch.setattr(digest_many, "scope_for", lambda raw: {})
    monkeypatch.setattr(digest_many.book_mod, "is_book", lambda path: False)
    monkeypatch.setattr(extract, "extract_text", lambda path, **k: open(path).read())
    monkeypatch.setattr(extract, "_template", lambda raw, scope: {"raw": raw})
    return tmp_path


def test_select_filters_by_topic_and_depth_and_orders_by_relevance(vault):
    assert digest_many.select(hub="series-k", topics={"comb"}) == ["raw/web-clips/k-2.md", "raw/web-clips/k-1.md"]
    assert digest_many.select(hub="series-k", topics={"comb", "tyi"}, limit=1) == ["raw/web-clips/k-2.md"]


def args(**kw):
    base = dict(run="r", hub="series-k", topics="comb", types="", depth="easy", raws_file=None, limit=None,
                model="sonnet", max_usd=10.0, dry_run=False, wait=1, max=0, retry=False)
    return SimpleNamespace(**{**base, **kw})


def test_submit_collect_drive_resume(vault, monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: sent.append(list(reqs)) or "batch_1")
    assert digest_many.cmd_submit(args()) == 0
    state = digest_many._load("r")
    assert [len(c) for c in sent] == [2] and set(state["targets"]) == {"raw/web-clips/k-1.md", "raw/web-clips/k-2.md"}
    assert all(t["status"] == "submitted" for t in state["targets"].values())
    assert digest_many.cmd_submit(args()) == 0 and len(sent) == 1        # nothing new: no second batch

    good = json.dumps({**GOOD, "raw": "raw/web-clips/k-1.md"})
    monkeypatch.setattr(llm, "collect", lambda bid, wait_s=0, root=None: [
        llm.Result(id=sent[0][0].id, text=good, usd=0.02, backend="batch", model="claude-sonnet-5-5"),
        llm.Result(id=sent[0][1].id, text="junk", usd=0.02, backend="batch", model="claude-sonnet-5-5")])
    assert digest_many.cmd_collect(args()) == 0
    state = digest_many._load("r")
    assert state["spent"] == pytest.approx(0.04)
    status = {raw: t["status"] for raw, t in state["targets"].items()}
    assert sorted(status.values()) == ["filled", "rejected"]
    filled = next(raw for raw, s in status.items() if s == "filled")
    assert (vault / ".cache/digest-many/r/claims" / f"{state['targets'][filled]['id']}.json").is_file()
    assert any((vault / ".cache/digest-many/r/drafts").iterdir())

    done = []
    monkeypatch.setattr(digest_many, "digest_one", lambda raw, path: done.append(raw))
    assert digest_many.cmd_drive(args()) == 0 and done == [filled]
    assert digest_many._load("r")["targets"][filled]["status"] == "finalized"
    assert digest_many.cmd_drive(args()) == 0 and done == [filled]       # resumable: nothing left to do


def test_drive_stops_after_three_failures_in_a_row(vault, monkeypatch):
    state = digest_many._load("r")
    for n in range(5):
        state["targets"][f"raw/{n}.md"] = {"id": f"s{n}", "status": "filled", "usd": 0, "note": ""}
    digest_many._save(state)
    calls = []

    def boom(raw, path):
        calls.append(raw)
        raise RuntimeError("finalize failed")

    monkeypatch.setattr(digest_many, "digest_one", boom)
    assert digest_many.cmd_drive(args()) == 1 and len(calls) == digest_many.STOP_AFTER


def test_submit_refuses_a_run_over_the_cap(vault, monkeypatch):
    monkeypatch.setattr(llm, "submit", lambda *a, **k: pytest.fail("over the cap: nothing is sent"))
    assert digest_many.cmd_submit(args(max_usd=0.0)) == 2


def test_identical_clips_get_distinct_request_ids_and_books_are_skipped(vault, monkeypatch):
    (vault / "raw/web-clips/k-9.md").write_text((vault / "raw/web-clips/k-1.md").read_text())    # same bytes
    a, _ = digest_many.build_request("raw/web-clips/k-1.md")
    b, _ = digest_many.build_request("raw/web-clips/k-9.md")
    assert a.id != b.id
    monkeypatch.setattr(digest_many.book_mod, "is_book", lambda path: True)
    req, why = digest_many.build_request("raw/web-clips/k-1.md")
    assert req is None and "book" in why


def test_submit_registers_targets_only_when_their_batch_exists_and_retry_resends(vault, monkeypatch):
    def boom(reqs, root=None):
        raise llm.LLMError("api down")

    monkeypatch.setattr(llm, "submit", boom)
    with pytest.raises(llm.LLMError):
        digest_many.cmd_submit(args())
    assert digest_many._load("r")["targets"] == {}                      # nothing recorded: a re-run resends them
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: "b1")
    assert digest_many.cmd_submit(args()) == 0
    state = digest_many._load("r")
    state["targets"]["raw/web-clips/k-1.md"]["status"] = "rejected"
    digest_many._save(state)
    sent = []
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: sent.append([r.id for r in reqs]) or "b2")
    digest_many.cmd_submit(args())
    assert sent == []                                                  # rejected stays put without --retry
    digest_many.cmd_submit(args(retry=True))
    assert sent == [[digest_many.request_id("raw/web-clips/k-1.md")]]


def test_drive_refuses_a_source_with_an_open_session_and_skips_an_already_full_page(vault, monkeypatch):
    state = digest_many._load("r")
    state["targets"]["raw/web-clips/k-1.md"] = {"id": "a", "status": "filled", "usd": 0, "note": ""}
    state["targets"]["raw/web-clips/k-4.md"] = {"id": "b", "status": "filled", "usd": 0, "note": ""}
    digest_many._save(state)
    monkeypatch.setattr(digest_many, "existing_digest_for_raw",
                        lambda raw: "wiki/blog-k-4.md" if raw.endswith("k-4.md") else None)
    monkeypatch.setattr(digest_many.session_mod, "find_open_session", lambda raw: "abc")
    assert digest_many.cmd_drive(args()) == 0
    after = digest_many._load("r")["targets"]
    assert after["raw/web-clips/k-4.md"]["status"] == "finalized"         # depth: full already: no second session
    assert after["raw/web-clips/k-1.md"]["status"] == "failed" and "already open" in after["raw/web-clips/k-1.md"]["note"]


def test_merge_handles_crlf_pages():
    out = merge_frontmatter(OLD.replace("\n", "\r\n"), NEW)
    assert fields(out)["blog"] == '"Combinatorics and More"' and fields(out)["depth"] == "full"


def test_map_plans_the_existing_page_not_a_second_one(vault, monkeypatch):
    from kb_distillery.ingest import map as map_mod
    monkeypatch.setattr(map_mod, "ROOT", str(vault))
    monkeypatch.setattr(map_mod, "existing_digest_for_raw", lambda raw: "wiki/blog-k-1.md" if raw.endswith("k-1.md") else None)
    (vault / "wiki" / "blog-k-1.md").write_text("---\ntype: blog-post\nraw: raw/web-clips/k-1.md\n---\n# P\n")
    assert map_mod._existing_page("raw/web-clips/k-1.md", "article", "article-k-1") == ("blog-post", "blog-k-1")
    assert map_mod._existing_page("raw/web-clips/k-9.md", "article", "article-k-9") == ("article", "article-k-9")
