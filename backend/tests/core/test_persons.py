import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

from kb.paths import CODE_DIR as HERE
from kb.core import persons

V2 = """---
type: person
layer: concept
url: https://example.org/~ada
scholar: none
github: https://github.com/ada
email: ada@example.org
advisors: [charles-babbage]
students: []
verified: 2026-10-21
---

# Ada Lovelace

First programmer.

## Repos
<!-- from: github -->

| Repo | Stars | What | Ingest |
|---|---|---|---|
| [engine](https://github.com/ada/engine) | 12 | notes | index |

## Why it matters here

- [[theme-learning-theory]] — the thread

## Field notes

Custom prose that must survive.

## Meeting log

### 2026-10-01
- Discussed: engines
- Action: none
"""

PAGES = {"theme-learning-theory": {"type": "topic"},
         "charles-babbage": {"type": "person", "students": ["ada-lovelace"]}}


class ParseRenderTest(unittest.TestCase):
    def test_round_trip(self):
        fm, body = persons.parse_frontmatter(V2)
        head, sections = persons.parse_sections(body)
        self.assertEqual(fm["advisors"], ["charles-babbage"])
        self.assertEqual([s["title"] for s in sections], ["Repos", "Why it matters here", "Field notes", "Meeting log"])
        self.assertEqual(sections[0]["source"], "github")
        self.assertIsNone(sections[1]["source"])
        self.assertEqual(persons.render(fm, head, sections), V2)

    def test_merge_keeps_hand_sections_and_replaces_generated(self):
        _fm, body = persons.parse_frontmatter(V2)
        generated = [{"title": "Repos", "source": "github", "body": "- new"},
                     {"title": "Courses", "source": "manual", "body": "- c"}]
        head, sections = persons.merge(body, generated)
        titles = [s["title"] for s in persons.order(sections)]
        self.assertEqual(titles, ["Repos", "Courses", "Why it matters here", "Field notes", "Meeting log"])
        self.assertIn("Discussed: engines", next(s["body"] for s in sections if s["title"] == "Meeting log"))
        self.assertEqual(next(s["body"] for s in sections if s["title"] == "Repos"), "- new")

    def test_sections_from_manifest(self):
        m = {"roles": [{"from": "2020", "org": "TAU", "role": "Prof", "source": "manual"}],
             "papers": [{"slug": "2020-x", "title": "X", "year": 2020, "citation_count": 500,
                         "tier_emoji": "⭐", "author_count": 40},
                        {"slug": "2019-y", "title": "Y", "year": 2019, "citation_count": 10,
                         "tier_emoji": "🥉", "pin": True},
                        {"kind": "book", "title": "B", "url": "http://b", "year": 2001}],
             "courses": [{"title": "C", "url": "http://c", "source": "manual"}]}
        secs = {s["title"]: s for s in persons.sections_from_manifest(m, {"paper-2019-y"}, ["paper-2019-y"])}
        self.assertEqual(set(secs), {"Roles & companies", "Courses", "Bibliography", "Cataloged in vault"})
        bib = secs["Bibliography"]["body"].split("\n")
        self.assertTrue(bib[-3].startswith("| 📌 | 2019 | [[paper-2019-y\\|Y]]"))   # pinned first, linked
        self.assertTrue(bib[-2].startswith("| 🚫 | 2020 | X"))                       # mega-author
        self.assertTrue(bib[-1].startswith("| 📖 | 2001 | [B](http://b)"))
        self.assertEqual(secs["Courses"]["source"], "manual")


class CheckTest(unittest.TestCase):
    def check(self, text, pages=PAGES, slug="ada-lovelace"):
        fm, body = persons.parse_frontmatter(text)
        return persons.check(slug, fm, body, pages)

    def test_valid_verified_page(self):
        errs, warns, stats = self.check(V2.replace("verified: 2026-10-21",
                                                   "youtube: none\nblog: none\nwikipedia: unknown\norgs: []\nverified: 2026-10-21"))
        self.assertEqual(errs, [])
        self.assertEqual(stats["unverified"], 0)
        self.assertEqual(stats["unknowns"], 1)

    def test_verified_page_must_state_every_handle(self):
        errs, _w, _s = self.check(V2)
        self.assertTrue(any("must state `youtube:`" in e for e in errs))

    def test_legacy_fields_are_errors(self):
        errs, _w, _s = self.check(V2.replace("type: person", "type: person\nstatus: seed\narea: [x]"))
        self.assertTrue(any("`status:` is not a person field" in e for e in errs))
        self.assertTrue(any("`area:` is not a person field" in e for e in errs))

    def test_summary_fields_are_person_fields(self):
        errs, _w, _s = self.check(V2.replace("type: person", 'type: person\nsummary: "x"\nsummary_from: abc\nsummary_by: me'))
        self.assertFalse(any("summary" in e for e in errs))

    def test_unverified_page_is_backlog_not_error(self):
        text = V2.replace("verified: 2026-10-21\n", "")
        errs, warns, stats = self.check(text)
        self.assertEqual(errs, [])
        self.assertEqual(stats["unverified"], 1)

    def test_section_against_none_handle(self):
        errs, _w, _s = self.check(V2.replace("github: https://github.com/ada", "github: none"))
        self.assertTrue(any("## Repos is generated from `github:` but it is `none`" in e for e in errs))

    def test_why_needs_theme_or_concept_link(self):
        text = V2.replace("- [[theme-learning-theory]] — the thread", "- nothing linked")
        errs, _w, _s = self.check(text)
        self.assertTrue(any("links no topic or idea" in e for e in errs))
        errs, warns, _s = self.check(text.replace("verified: 2026-10-21\n", ""))
        self.assertEqual(errs, [])
        self.assertTrue(any("links no topic or idea" in w for w in warns))

    def test_lineage_reciprocity_and_stubs(self):
        pages = {**PAGES, "charles-babbage": {"type": "person", "students": []}}
        _e, warns, stats = self.check(V2, pages)
        self.assertTrue(any("does not list [[ada-lovelace]]" in w for w in warns))
        _e, _w, stats = self.check(V2.replace("[charles-babbage]", "[nobody-yet]"))
        self.assertEqual(stats["stubs"], {"nobody-yet"})

    def test_duplicate_identity(self):
        fm, body = persons.parse_frontmatter(V2.replace("scholar: none", "scholar: https://scholar.google.com/citations?user=A"))
        other = dict(fm)
        errs, _w, _h = persons.check_all({"ada-lovelace": (fm, body), "ada-two": (other, body)},
                                         {**PAGES, "ada-lovelace": fm, "ada-two": other})
        self.assertTrue(any("one person, two pages" in m for _s, m in errs))


OLD_HAND = """---
type: person
area: [depth-vs-width, amit-daniely, info-theory]
status: growing
role: thesis-instructor
optional: true
affiliation: HUJI — School of CS
lab: Google Research (part-time)
email: amit@example.org
url: https://www.cs.huji.ac.il/~amitd/
scholar: https://scholar.google.com/citations?user=X
related: [depth-vs-width]
---

# Amit Daniely

HUJI — School of CS · thesis instructor *(optional)*. Why depth helps.

## Research themes
- Why depth helps
- See bibliography below for full publication list

## Concepts
- [[depth-vs-width]]

## Bibliography

Citations from [Google Scholar](https://scholar.google.com/citations?user=X) (Aug 2026).

| | Year | Title | Venue | Citations |
|---|------|-------|-------|-----------|
| 🥉 | 2017 | [[paper-2017-depth-separation\\|Depth Separation]] | COLT 2017 | 12 |

### Suggested reading (thesis-relevant)

| | Paper | Why |
|---|-------|-----|
| ⭐ | [[paper-2017-depth-separation]] | why depth |

## Meeting log

### 2026-09-01
- Discussed: a thing
- Action: another
"""

OLD_GENERATED = """---
type: person
area: [moc-quantum, gil-kalai]
status: seed
affiliation: HUJI (emeritus)
url: https://ma.huji.ac.il/~kalai/
scholar: https://scholar.google.com/citations?user=K
related: [theme-quantum]
---

# Gil Kalai

HUJI (emeritus). Indexed from Semantic Scholar (171 papers).

## Research themes

- Boolean functions

## Concepts

- [[theme-quantum]]

## Bibliography

Citations from Semantic Scholar (indexed 2026-09-14). Influence tiers: ⭐ ≥200 · 🥈 50–199 · 🥉 other.

| | Year | Title | Venue | Citations |
|---|------|-------|-------|-----------|
| ⭐ | 1998 | [Noise sensitivity](https://arxiv.org/abs/x) | Publ. IHES | 700 |

## Books & monographs

- [Discrete Mathematics](http://x/dmc.pdf) (2001) — with M. Parnas

## Blog

- [[series-gil-kalai-blog]] — *Combinatorics and More*

## Teaching

- [Game Theory](https://gilkalai.wordpress.com/) — listed on blog

## Cataloged in vault

Star-tier papers with PDF stubs (`depth: catalog`):

- (none cataloged yet)

## Meeting log

### YYYY-MM-DD
- Discussed:
- Action:
"""


def _load_migration():
    path = os.path.join(HERE, "migrations", "0006_person_v2.py")
    spec = importlib.util.spec_from_file_location("m0006", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MigrationTest(unittest.TestCase):
    """A throw-away vault: two old-layout pages, the pages they link, no manifests."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "meta"))
        pages = {"amit-daniely": OLD_HAND, "gil-kalai": OLD_GENERATED,
                 "depth-vs-width": "---\ntype: idea\nlayer: concept\nstatus: seed\n---\n\n# d\n",
                 "theme-quantum": "---\ntype: topic\nlayer: concept\nstatus: seed\n---\n\n# q\n",
                 "paper-2017-depth-separation": "---\ntype: paper\n---\n\n# p\n",
                 "series-gil-kalai-blog": "---\ntype: series\nurl: https://gilkalai.wordpress.com/\n---\n\n# s\n"}
        for slug, text in pages.items():
            with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
                f.write(text)
        with open(os.path.join(self.root, "meta", "corpus.tsv"), "w", encoding="utf-8") as f:
            f.write("# generated\nraw/printed-docs/2017-d.pdf\tsha\tpdf\tdigested\tpaper-2017-depth-separation\tamit-daniely\n")
        self.mod = _load_migration()
        self.persons, self.researcher = self.mod._mods(self.root)
        self._root_backup = self.researcher.ROOT
        self.researcher.ROOT = self.root
        self.researcher.RESEARCHER_ROOT = os.path.join(self.root, "meta", ".researcher")

    def tearDown(self):
        self.researcher.ROOT = self._root_backup
        self.researcher.RESEARCHER_ROOT = os.path.join(self._root_backup, "meta", ".researcher")
        shutil.rmtree(self.root)

    def test_every_old_line_is_accounted_for(self):
        results = self.mod.plan(self.root)
        self.assertEqual(set(results), {"amit-daniely", "gil-kalai"})
        for slug, (_text, _m, rows) in results.items():
            self.assertEqual([l for st, l in rows if st == "UNACCOUNTED"], [], slug)

    def test_hand_page(self):
        text, m, _rows = self.mod.plan(self.root)["amit-daniely"]
        fm, body = persons.parse_frontmatter(text)
        self.assertEqual(fm, {"type": "person", "layer": "concept", "url": "https://www.cs.huji.ac.il/~amitd/",
                              "scholar": "https://scholar.google.com/citations?user=X", "email": "amit@example.org"})
        self.assertIn("HUJI — School of CS. Candidate thesis instructor. Why depth helps.", body)
        self.assertIn("| ? | — | HUJI — School of CS · Google Research (part-time) | — |", body)
        why = persons.section if hasattr(persons, "section") else None
        self.assertIn("**Concepts:** [[depth-vs-width]]", body)
        self.assertIn("**Also linked:** `theme-info-theory` (no page)", body)      # bare area slug → theme-
        self.assertIn("### Suggested reading (thesis-relevant)", body)
        self.assertIn("- Discussed: a thing", body)
        self.assertNotIn("See bibliography below", body)
        self.assertEqual([p["wiki"] for p in m["papers"]], ["paper-2017-depth-separation"])
        self.assertEqual(m["papers"][0]["source"], "manual")
        self.assertIn("- [[paper-2017-depth-separation]]", body)                 # from corpus collection
        errs, _w, _s = persons.check("amit-daniely", fm, body, {"depth-vs-width": {"type": "idea"}})
        self.assertEqual(errs, [])

    def test_generated_page_with_blog_books_teaching(self):
        text, m, _rows = self.mod.plan(self.root)["gil-kalai"]
        fm, body = persons.parse_frontmatter(text)
        self.assertEqual(fm["blog"], "https://gilkalai.wordpress.com/")
        self.assertNotIn("Indexed from Semantic Scholar", body.split("## ")[0])
        self.assertIn("171 papers indexed", body)
        self.assertIn("| 📖 | 2001 | [Discrete Mathematics](http://x/dmc.pdf) (2001) — with M. Parnas | — | — |", body)
        self.assertIn("## Writing\n<!-- from: manual -->\n\n- [[series-gil-kalai-blog]] — *Combinatorics and More*", body)
        self.assertIn("## Courses\n<!-- from: manual -->\n\n- [Game Theory]", body)
        self.assertNotIn("none cataloged yet", body)
        self.assertIn("**Concepts:** [[theme-quantum]]", body)
        self.assertNotIn("moc-quantum", body)
        self.assertEqual([c["title"] for c in m["courses"]], ["Game Theory"])

    def test_apply_is_idempotent(self):
        self.mod.apply(self.root)
        with open(os.path.join(self.root, "wiki", "amit-daniely.md"), encoding="utf-8") as f:
            first = f.read()
        self.assertTrue(os.path.isfile(os.path.join(self.root, "meta", ".researcher", "amit-daniely", "manifest.json")))
        self.assertEqual(self.mod.plan(self.root), {})          # nothing left to migrate
        self.mod.apply(self.root)
        with open(os.path.join(self.root, "wiki", "amit-daniely.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), first)


class WriteBackTest(unittest.TestCase):
    """finalize must not clobber hand-written sections (the pre-0.12 bug)."""

    def test_write_person_wiki_preserves_hand_sections(self):
        from kb.ingest import researcher
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "wiki"))
        with open(os.path.join(root, "wiki", "ada-lovelace.md"), "w", encoding="utf-8") as f:
            f.write(V2)
        backup = researcher.ROOT
        researcher.ROOT = root
        try:
            researcher._write_person_wiki({"slug": "ada-lovelace", "name": "Ada Lovelace",
                                           "handles": {"github": "https://github.com/ada", "url": "none"},
                                           "repos": [{"title": "new-engine", "url": "http://e", "source": "github"}],
                                           "papers": [], "verified": "2026-10-22"})
            with open(os.path.join(root, "wiki", "ada-lovelace.md"), encoding="utf-8") as f:
                out = f.read()
        finally:
            researcher.ROOT = backup
            shutil.rmtree(root)
        self.assertIn("Custom prose that must survive.", out)
        self.assertIn("- Discussed: engines", out)
        self.assertIn("[new-engine](http://e)", out)
        self.assertNotIn("[engine](https://github.com/ada/engine)", out)
        self.assertIn("url: none", out)
        self.assertIn("verified: 2026-10-22", out)
        self.assertIn("advisors: [charles-babbage]", out)        # page-only key kept


if __name__ == "__main__":
    unittest.main()
