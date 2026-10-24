"""Light checks for the graph page's mouse scheme (the browser run is `pixi run test-e2e`)."""
import re
import unittest
from pathlib import Path

from kb.paths import CODE_DIR

DASH = Path(CODE_DIR) / "dashboard"
STATIC = DASH / "static"
DIALOG = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")


class GraphUiTests(unittest.TestCase):
    def setUp(self):
        self.html = (DASH / "graph.html").read_text(encoding="utf-8")

    def test_graph_page_loads_the_mouse_layer(self):
        self.assertIn("/static/graph-mouse.js", self.html)

    def test_no_interaction_modes_left(self):
        self.assertNotIn("mode-btn", self.html)
        self.assertNotIn('data-fly="mode"', self.html)
        for name in ("graph.js", "graph-shell.js"):
            self.assertNotIn("setInteractionMode", (STATIC / name).read_text(encoding="utf-8"), name)

    def test_search_bar_has_no_cmd_k(self):
        self.assertNotIn("⌘K", self.html)
        shell = (STATIC / "graph-shell.js").read_text(encoding="utf-8")
        self.assertNotIn('e.key.toLowerCase() === "k"', shell)

    def test_l_key_no_longer_lassos(self):
        sel = (STATIC / "selection.js").read_text(encoding="utf-8")
        self.assertNotIn('e.key === "l"', sel)
        self.assertNotIn("sel-lasso-btn", sel)

    def test_node_menu_offers_genealogy(self):
        menu = (STATIC / "graph-mouse.js").read_text(encoding="utf-8")
        for item in ('id: "reader"', 'id: "explore"', 'id: "genealogy"'):
            self.assertIn(item, menu)
        self.assertIn("openCitations({ focus", menu)

    def test_explore_has_an_embed_mode(self):
        self.assertIn("ex-embed", (DASH / "explore.html").read_text(encoding="utf-8"))
        self.assertIn(".ex-embed", (STATIC / "explore.css").read_text(encoding="utf-8"))

    def test_magnetic_pointer_is_an_opt_out_experiment(self):
        self.assertIn("/static/graph-magnet.js", self.html)
        for box in ('id="magnet-pointer" checked', 'id="declutter-labels" checked'):
            self.assertIn(box, self.html)
        magnet = (STATIC / "graph-magnet.js").read_text(encoding="utf-8")
        self.assertIn("REACH_MIN = 12, REACH_MAX = 90", magnet)
        self.assertIn('insertAdjacentElement("afterend"', magnet)   # not inside force-graph's container

    def test_calm_hover_gates_and_fades_the_focus(self):
        self.assertIn('id="calm-hover" checked', self.html)
        graph = (STATIC / "graph.js").read_text(encoding="utf-8")
        for needle in ("function requestHover", "hoverTuning", "focused: () => hoveredNode", "prevFocus"):
            self.assertIn(needle, graph)
        self.assertNotIn("r * 1.45", graph)   # a ring marks the hovered node; growing it moves edges and labels
        magnet = (STATIC / "graph-magnet.js").read_text(encoding="utf-8")
        self.assertIn("LEAVE = 1.3", magnet)

    def test_no_browser_dialogs(self):
        for name in ("graph-mouse.js", "graph-shell.js", "datalayer.js", "graph-magnet.js"):
            text = (STATIC / name).read_text(encoding="utf-8")
            self.assertIsNone(DIALOG.search(text), f"{name} uses a browser dialog")


if __name__ == "__main__":
    unittest.main()
