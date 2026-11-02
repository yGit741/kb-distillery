"""Which pages a first-time reader should see — the Python twin of
`web/src/features/graph/publicPredicate.ts` (`isPublic`). Keep the two in step: the app's "Map"
view and a public snapshot built with `share snapshot … --predicate public` must draw the same pages.

The rule, on a graph node as `/api/graph` reports it (`type`, `layer`, `depth`, `inDegree`, `outDegree`):

  - aux types (`scope`, `distilled-think`) never;
  - topics always (they anchor the layout);
  - sources (layer `source`) only when read in depth — `depth` full or deep; a listed or skimmed import
    is not knowledge yet;
  - everything else (ideas, questions, people, collections, …) when at least one link reaches or leaves
    it: inDegree + outDegree >= 1.

Degrees are the full graph's: `kb_distillery.graph.snapshot.build_graph_snapshot` counts them over every wiki page
before any share cut, and `build.apply_profile` never recomputes them — so a page keeps the degree the
API shows even when the public profile or this predicate drops some of its neighbours.
"""

PUBLIC = "public"
PREDICATES = (PUBLIC,)

AUX_TYPES = frozenset({"scope", "distilled-think"})
DEEP_DEPTHS = frozenset({"full", "deep"})


def degree_of(node: dict) -> int:
    """inDegree + outDegree as the graph snapshot carries them (missing → 0)."""
    return int(node.get("inDegree") or 0) + int(node.get("outDegree") or 0)


def is_public(node: dict) -> bool:
    ntype = node.get("type") or ""
    if ntype in AUX_TYPES:
        return False
    if ntype == "topic":
        return True
    if node.get("layer") == "source":
        return (node.get("depth") or "") in DEEP_DEPTHS
    return degree_of(node) >= 1


def predicate_fn(predicate):
    """The node test for a predicate id; None for no predicate. Unknown ids are a ValueError."""
    if predicate in (None, ""):
        return None
    if predicate == PUBLIC:
        return is_public
    raise ValueError(f"unknown predicate {predicate!r}; choose one of {', '.join(PREDICATES)}")


def add_predicate_args(parser):
    """`--predicate` / `--view`, shared by `share build`, `audit` and `snapshot`."""
    parser.add_argument("--predicate", choices=PREDICATES, default=None,
                        help="public only: keep just the pages the app's Map view draws (kb_distillery.publish.site.predicate)")
    parser.add_argument("--view", default=None, metavar="ID",
                        help="graph view the app opens on (e.g. map); app layout, lands as home.view")
