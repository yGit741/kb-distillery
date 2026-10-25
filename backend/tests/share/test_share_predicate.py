"""`share … --predicate public`: kb.share.predicate.is_public (the twin of
frontend/src/features/graph/publicPredicate.test.ts — same five cases) and the blob cut it drives."""
import unittest

from kb.share.build import apply_predicate, apply_profile, drop_pages
from kb.share.contracts import Manifest
from kb.share.home import apply_home
from kb.share.predicate import is_public, predicate_fn


def node(**p):
    base = {"id": "x", "title": "", "layer": "concept", "type": "idea", "areas": [], "inDegree": 0, "outDegree": 0}
    base.update(p)
    return base


class TestIsPublic(unittest.TestCase):
    def test_keeps_topics_even_without_links(self):
        self.assertTrue(is_public(node(type="topic")))

    def test_keeps_linked_concepts_and_collections_drops_orphans(self):
        self.assertTrue(is_public(node(type="idea", inDegree=1)))
        self.assertTrue(is_public(node(type="question", outDegree=2)))
        self.assertTrue(is_public(node(layer="collection", type="series", inDegree=3)))
        self.assertFalse(is_public(node(type="idea")))

    def test_keeps_only_sources_read_in_depth(self):
        self.assertTrue(is_public(node(layer="source", type="paper", depth="deep", inDegree=4)))
        self.assertTrue(is_public(node(layer="source", type="paper", depth="full")))
        self.assertFalse(is_public(node(layer="source", type="article", depth="easy", inDegree=9)))
        self.assertFalse(is_public(node(layer="source", type="paper", depth="listed")))

    def test_never_shows_aux_types(self):
        self.assertFalse(is_public(node(type="scope", inDegree=5)))
        self.assertFalse(is_public(node(type="distilled-think", inDegree=5)))

    def test_resolves_by_id(self):
        self.assertIs(predicate_fn("public"), is_public)
        self.assertIsNone(predicate_fn(None))
        self.assertIsNone(predicate_fn(""))
        with self.assertRaises(ValueError):
            predicate_fn("everything")


def blob():
    """topic t, deep paper p, easy article a (linked from everywhere), idea i linked only by a, orphan o."""
    nodes = [
        node(id="t", type="topic", inDegree=0, outDegree=2),
        node(id="p", layer="source", type="paper", depth="deep", inDegree=1, outDegree=1),
        node(id="a", layer="source", type="article", depth="easy", inDegree=2, outDegree=1),
        node(id="i", type="idea", inDegree=1, outDegree=0),
        node(id="o", type="idea"),
    ]
    links = [{"source": "t", "target": "p", "kind": "wikilink"}, {"source": "t", "target": "a", "kind": "wikilink"},
             {"source": "p", "target": "a", "kind": "wikilink"}, {"source": "a", "target": "i", "kind": "wikilink"}]
    concept_links = [{"source": "t", "target": "i", "via": ["a"]}]
    index = {"pages": [{"id": n["id"], "type": n["type"]} for n in nodes],
             "links": [["t", "p"], ["t", "a"], ["p", "a"], ["a", "i"]],
             "wanted": [{"slug": "missing", "from": ["a", "t"]}]}
    pages = {n["id"]: {"card": {"id": n["id"], "type": n["type"]}, "markdown": f"# {n['id']}\n", "backlinks": [],
                       "outbound": [], "suggested": []} for n in nodes}
    pages["i"]["backlinks"] = [{"id": "a"}]
    pages["t"]["outbound"] = ["p", "a"]
    pages["p"]["suggested"] = [{"id": "i", "via": ["a"]}, {"id": "a", "via": []}]
    return {"graph": {"nodes": nodes, "links": links, "concept_links": concept_links, "facets": {"types": []}},
            "index": index, "pages": pages}


class TestApplyPredicate(unittest.TestCase):
    def test_no_predicate_keeps_todays_behaviour(self):
        data = apply_profile(blob(), "public")
        before = {n["id"] for n in data["graph"]["nodes"]}
        out, dropped = apply_predicate(data, None)
        self.assertEqual(dropped, 0)
        self.assertEqual({n["id"] for n in out["graph"]["nodes"]}, before)

    def test_drops_failing_pages_everywhere(self):
        data, dropped = apply_predicate(apply_profile(blob(), "public"), "public")
        self.assertEqual(dropped, 2)                                  # graph nodes: a (easy article), o (orphan)
        kept = {n["id"] for n in data["graph"]["nodes"]}
        # i keeps its FULL-graph degree (1, from the easy article) and so stays: degrees are the API's, not recomputed
        self.assertEqual(kept, {"t", "p", "i"})
        g = data["graph"]
        self.assertEqual([(l["source"], l["target"]) for l in g["links"]], [("t", "p")])
        self.assertEqual(g["concept_links"], [{"source": "t", "target": "i", "via": []}])   # via filtered like suggested
        self.assertEqual((g["node_count"], g["link_count"]), (3, 1))
        self.assertEqual(g["facets"]["types"], ["idea", "paper", "topic"])
        self.assertEqual({c["id"] for c in data["index"]["pages"]}, {"t", "p", "i"})   # no card → "Show all" can't list it
        self.assertEqual(data["index"]["links"], [["t", "p"]])
        self.assertEqual(data["index"]["wanted"][0]["from"], ["t"])
        self.assertEqual(set(data["pages"]), {"t", "p", "i"})                           # no body either
        self.assertEqual(data["pages"]["i"]["backlinks"], [])
        self.assertEqual(data["pages"]["t"]["outbound"], ["p"])
        self.assertEqual(data["pages"]["p"]["suggested"], [{"id": "i", "via": []}])

    def test_degrees_are_read_before_dropping(self):
        """Dropping `a` must not demote `i` to an orphan: the rule sees the full graph's degrees."""
        data, _ = apply_predicate(apply_profile(blob(), "public"), "public")
        i = next(n for n in data["graph"]["nodes"] if n["id"] == "i")
        self.assertEqual((i["inDegree"], i["outDegree"]), (1, 0))

    def test_card_or_body_without_a_node_goes_too(self):
        data = blob()
        data["index"]["pages"].append({"id": "ghost", "type": "idea"})
        data["pages"]["ghost"] = {"card": {"id": "ghost", "type": "idea"}, "markdown": "# ghost\n"}
        out, dropped = apply_predicate(data, "public")
        self.assertEqual(dropped, 2)                                  # the ghost is no graph node: removed, not counted
        self.assertNotIn("ghost", out["pages"])
        self.assertNotIn("ghost", {c["id"] for c in out["index"]["pages"]})

    def test_kept_pages_do_not_name_dropped_slugs(self):
        data = blob()
        data["pages"]["t"]["markdown"] = "# t\n\nSee [[a|the article]] and [[p]] and [[o]].\n"
        data["pages"]["t"]["frontmatter"] = {"related": ["a", "p"], "sources": ["a"]}
        data["pages"]["a"]["card"]["title"] = "The article"
        data["pages"]["o"]["card"]["title"] = "Orphan"
        data["graph"]["nodes"][0]["properties"] = {"related": "a, p"}
        data["index"]["pages"][0]["related"] = ["a", "p"]
        out, _ = apply_predicate(apply_profile(data, "public"), "public")
        t = out["pages"]["t"]
        self.assertEqual(t["markdown"], "# t\n\nSee the article and [[p]] and Orphan.\n")
        self.assertEqual(t["frontmatter"], {"related": ["p"], "sources": []})
        self.assertEqual(out["graph"]["nodes"][0]["properties"], {"related": "p"})
        self.assertEqual(next(c for c in out["index"]["pages"] if c["id"] == "t")["related"], ["p"])

    def test_drop_pages_is_the_shared_cut(self):
        data = drop_pages(blob(), {"a"})
        self.assertNotIn("a", set(data["pages"]))
        self.assertTrue(all("a" not in (l["source"], l["target"]) for l in data["graph"]["links"]))

    def test_home_cards_follow_the_cut_and_carry_the_view(self):
        data, _ = apply_predicate(apply_profile(blob(), "public"), "public")
        data = apply_home(data, {"cards": [{"title": "T", "pages": ["a", "o"]}, {"title": "K", "pages": ["t", "a"]}], "tour": None},
                          view="map")
        self.assertEqual(data["home"], {"cards": [{"title": "K", "pages": ["t"]}], "tour": None, "view": "map"})
        self.assertNotIn("view", apply_home(blob(), {"cards": [], "tour": None})["home"])


class TestStoryIds(unittest.TestCase):
    def test_reads_views_ts_from_a_worktree_and_handles_a_missing_file(self):
        import tempfile
        from pathlib import Path
        from kb.share.build import STORIES_FILE, story_ids
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(story_ids(d))
            f = Path(d) / STORIES_FILE
            f.parent.mkdir(parents=True)
            f.write_text('export const STORIES = [\n  {\n    id: "map",\n    name: "Map",\n  },\n  {\n    id: "thesis",\n  },\n];\n')
            self.assertEqual(story_ids(d), ["map", "thesis"])
        from kb.share.contracts import REPO
        self.assertIn("map", story_ids(REPO))


class TestManifest(unittest.TestCase):
    def test_records_predicate_dropped_and_view_only_when_set(self):
        base = dict(content_ref="main", content_sha="a" * 40, kb_version="1.0.0", viewer_sha="b" * 40,
                    profile="public", sha256="c" * 64, built_at="2026-10-25T00:00:00+00:00")
        plain = Manifest(**base).to_json()
        for k in ("predicate", "dropped", "view"):
            self.assertNotIn(f'"{k}"', plain)
        m = Manifest(**base, predicate="public", dropped=854, view="map")
        text = m.to_json()
        self.assertIn('"predicate": "public"', text)
        self.assertIn('"dropped": 854', text)
        self.assertIn('"view": "map"', text)
        self.assertEqual(Manifest.from_json(text), m)


if __name__ == "__main__":
    unittest.main()
