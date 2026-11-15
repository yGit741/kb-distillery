"""Free text → layer objects through the shared LLM tool (`kb_distillery.llm`); never Cypher.

The browser reads a `>` sentence with rules first (`web/src/features/graph/layers/sentence.ts`, no model). Text the rules
cannot read comes here: one prompt carries the query language (GRAMMAR below, kept in step with
`web/src/features/graph/layers/grammar.ts`), this kb's node types, edge types, areas and a sample of titles so names
resolve, and the model answers a JSON object `{"layers": [...], "explanation": "..."}`. The answer must validate as a list
of `Layer` (`kb_distillery.server.models.layers`, which mirrors the TypeScript model); anything else is a 422 that carries
the validation message and the raw text, never a guess.

Backends: `subscription` by default (`$KB_LLM_BACKEND`), falling back once to `api` when the subscription is unavailable,
fails or is rate-limited and a key exists; `batch` is accepted but waits minutes to hours, so it does not suit a line you
are typing.
"""
import json
import re

from pydantic import TypeAdapter, ValidationError

from kb_distillery import llm
from kb_distillery.config.flags import runtime
from kb_distillery.graph import query as cypher
from kb_distillery.graph.layers import Layer

MODEL = "haiku"
EFFORT = "low"
MAX_TOKENS = 2048
BATCH_WAIT_S = 300          # an interactive request does not wait for a batch for hours; it fails with a hint instead
BATCH_POLL_S = 5
TITLES_SHOWN = 40
NAMES_SHOWN = 30
DEFAULT_FALLBACK = "api"

# One line per layer, each line is one layer object. Keep in step with NODE_SPECS / EDGE_SPECS in grammar.ts
# (tests/fixtures/layers/*.json holds the lines both printers must produce).
GRAMMAR = """\
A layer is one of:
  show|hide nodes <condition> [and <condition> ...]       keep (show) or remove (hide) pages
  show|hide edges <condition> [and <condition> ...]       keep or remove links
  style nodes|edges color|size|width|label by <value> [for <condition> [and ...]]
Page conditions (kind "nodes"):
  all | type <t> [or <t> ...] | degree <op> <n> | within <n> hops of "<page>"|favorites|this
  | paths between "<page>" and "<page>" up to <n> hops | having edge <type> [exists = false]
  | linked_from type <t> | created > <days>d | in area "<area>" | about "<phrase>" | favorite
  | mentioned_in chat "<title>" | text "<phrase>" | name "<page>" [or "<page>" ...] | not <condition>
Link conditions (target "edges"): all | type <t> | count <op> <n> | direction in|out|both | between "<page>" and "<page>"
<op> is one of >= <= > < =. Names are page titles or slugs, quoted. Style values: color by
format|area|status|depth|recency|added|evidence|support|layer|degree|score|none; size by
connections|in|out|uniform|tier|evidence|score|gap|logdeg; width by thin|normal|thick; any other value is a page
property written {"by": "<property>"}.

READING A REQUEST
People type fast: read past typos ("orphnas", "colur", "theams") and missing commas ("only orphans color by theme" is
two layers). The legend's colour names map to values: theme -> area, type or kind -> format, maturity -> status,
digest status -> depth, date added -> added, recency -> recency, source count -> evidence, source support -> support.
Never answer color "type" (it draws as the theme). Words for links counted on screen: orphans or isolated -> degree = 0,
leaves -> degree = 1, hubs -> degree >= 8. "don't show", "exclude", "without", "no", "remove" mean hide.
Use favorite only when the request says favourite, starred or pinned. When the request asks for something no condition
expresses (a reading status, a year, an author), answer the nearest condition that is still true to it, such as the page
type, and say in the explanation what was left out."""

# Flag graph-algos: the graph-theory conditions the browser computes on the drawn graph, and the words that call them.
ALGO_GRAMMAR = """Graph-theory page conditions (computed on the pages drawn):
  shortest path between "<page>" and "<page>" | all shortest paths between "<page>" and "<page>"
  | common neighbours of "<page>" and "<page>" | largest component | component <n> | component of "<page>"
  | clique >= <n> | core <k> | cut vertex | bridge end | top <n> by betweenness|pagerank|degree|closeness
  | largest community | community <n> | community of "<page>"
A show|hide nodes layer may end in "expand <n>": its pages and the pages up to n links from them.
color by community|component colours each group of pages.
Graph-theory words: neighbours, ego network, "and their neighbours" -> expand 1 (or within <n> hops of a page); near,
close to, around a page -> within 1 hop of it; how two pages connect, the path from A to B -> shortest path;
important, central, influential, bridging -> top 20 by betweenness; most cited, authority -> top 20 by pagerank;
clusters, groups, communities -> color by community (or a community); dense part, core -> core 3; bottleneck, single
point of failure, articulation point -> cut vertex; islands, disconnected parts -> color by component."""

ALGO_SHAPES = """Graph-theory conditions: {"t":"shortest","a":"<page>","b":"<page>"} (add "all":true for all shortest paths)
  {"t":"common","a":"<page>","b":"<page>"} {"t":"component","rank":1} {"t":"component","of":"<page>"}
  {"t":"clique","min":3} {"t":"core","k":3} {"t":"cut"} {"t":"bridge"}
  {"t":"top","by":"betweenness"|"pagerank"|"degree"|"closeness","n":20} {"t":"community","rank":1}
  {"t":"community","of":"<page>"}; a show or hide layer on nodes may carry "expand": n."""

# Layer objects as the browser holds them: "t" names the condition, the lines above are only for reading.
SHAPES = """\
Layer: {"id": "", "kind": "show"|"hide"|"style", "target": "nodes"|"edges", "subgraph": {"nodes": [cond...]} or
  {"edges": [cond...]} (or {} for every page or link), "style": {"color"|"size"|"width": value, "label": text} only for
  kind "style", "text": ""}
Node conditions: {"t":"type","value":"paper" or ["paper","idea"]} {"t":"degree","op":">=","n":3}
  {"t":"hops","of":"<page>"|"$favorites"|"$focus","n":2} {"t":"paths","a":"<page>","b":"<page>","n":3}
  {"t":"hasEdge","type":"contradicts","exists":false (omit for "has")} {"t":"linkedFromType","type":"paper"}
  {"t":"createdWithin","days":30} {"t":"inArea","area":"<area>"} {"t":"about","phrase":"..."} {"t":"favorite"}
  {"t":"mentionedIn","chat":"<title>"} {"t":"text","phrase":"..."} {"t":"name","slugs":["<page>"]}
  {"t":"not","cond":<node condition>} {"t":"all"}
Link conditions: {"t":"type","value":"supports"} {"t":"count","op":">","n":1} {"t":"direction","value":"in"|"out"|"both"}
  {"t":"endpoints","slugs":["<page>","<page>"]} {"t":"all"}"""

EXAMPLES = (
    ("only orphnas colour by theams",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "degree", "op": "=", "n": 0}]}},
      {"kind": "style", "target": "nodes", "subgraph": {}, "style": {"color": "area"}}]),
    ("only non-orphans within 3 hops of Learning theory",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "degree", "op": ">", "n": 0},
                                                                   {"t": "hops", "of": "Learning theory", "n": 3}]}}]),
    ("nodes that share a contradicts edge",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "hasEdge", "type": "contradicts"}]}}]),
    ("thicken contradicts edges and colour pages by area",
     [{"kind": "style", "target": "edges", "subgraph": {"edges": [{"t": "type", "value": "contradicts"}]},
       "style": {"width": "thick"}},
      {"kind": "style", "target": "nodes", "subgraph": {}, "style": {"color": "area"}}]),
    ("what connects Learning theory and Compression",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "paths", "a": "Learning theory",
                                                                   "b": "Compression", "n": 4}]}}]),
    ("my starred papers from 2020",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "type", "value": "paper"}, {"t": "favorite"}]}}],
     "Starred papers; the year is not a condition, so it is left out."),
)

ALGO_EXAMPLES = (
    ("the most important ideas and their neighbors",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "type", "value": "idea"},
                                                                   {"t": "top", "by": "betweenness", "n": 20}]},
       "expand": 1}]),
    ("how do i get from Learning theory to Compression, color the clusters",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "shortest", "a": "Learning theory",
                                                                   "b": "Compression"}]}},
      {"kind": "style", "target": "nodes", "subgraph": {}, "style": {"color": "community"}}]),
    ("pages that would split the graph if removed",
     [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "cut"}]}}]),
)


class LayersError(ValueError):
    """Text that cannot become layers: `message` says why; `status` is the HTTP status (422 for text, 502/400 when the
    LLM could not be asked)."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


# ---- vocabulary: what names the model may use
def vocabulary(graph=None):
    """{node_types, edge_types, areas: {name: count}, titles: [title]} of the kb's graph. Edge types are lower case
    (`contradicts`), like the sentences people type; the canvas matches them without regard to case."""
    g = cypher.current_graph() if graph is None else graph
    types, areas, titles = {}, {}, []
    for nid, d in g.nodes(data=True):
        if d.get("type"):
            types[d["type"]] = types.get(d["type"], 0) + 1
        for a in d.get("areas") or ():
            areas[a] = areas.get(a, 0) + 1
        titles.append((g.degree(nid), d.get("title") or nid))
    kinds = {}
    for _, _, d in g.edges(data=True):
        if d.get("kind"):
            k = str(d["kind"]).lower()
            kinds[k] = kinds.get(k, 0) + 1
    titles.sort(key=lambda t: (-t[0], t[1]))
    return {"node_types": dict(sorted(types.items())), "edge_types": dict(sorted(kinds.items())), "areas": _top(areas),
            "titles": [t for _, t in titles[:TITLES_SHOWN]]}


def _top(m):
    return dict(sorted(m.items(), key=lambda kv: (-kv[1], kv[0]))[:NAMES_SHOWN])


def _counts(m):
    return ", ".join(f"{k} ({n})" for k, n in m.items()) or "none"


def build_prompt(text, vocab, op="replace", algos=None):
    """The prompt for `text`. `algos` (default: flag graph-algos) adds the graph-theory conditions and words."""
    algos = runtime.effective("graph-algos") if algos is None else algos
    examples = EXAMPLES + ALGO_EXAMPLES if algos else EXAMPLES
    # an example may carry its explanation (what was left out); the rest explain nothing
    shots = "\n\n".join(f"Request: {q}\n" + json.dumps({"layers": ls, "explanation": ex[0] if ex else ""}) for q, ls, *ex in examples)
    grammar = f"{GRAMMAR}\n{ALGO_GRAMMAR}" if algos else GRAMMAR
    shapes = f"{SHAPES}\n{ALGO_SHAPES}" if algos else SHAPES
    titles = "; ".join(vocab.get("titles") or ()) or "none"
    intent = {"replace": "The layers replace the current view's show/hide layers.",
              "stack": "The layers are added on top of the current view.",
              "remove": "The request names a layer to take away: answer the layer it describes."}[op]
    return f"""You turn a request about a knowledge-base graph into layer objects: each layer shows pages or links, hides them, or styles them. Answer layers, never Cypher.

QUERY LANGUAGE (one line per layer; every line is one layer)
{grammar}

LAYER OBJECTS
{shapes}

THIS KNOWLEDGE BASE
Page types (count): {_counts(vocab.get("node_types") or {})}
Link types (count): {_counts(vocab.get("edge_types") or {})}
Areas (count): {_counts(vocab.get("areas") or {})}
Some page titles: {titles}
Use only these types and areas. Write a page name as the title it has here; if the request names a page that is not listed, still write the name as given.

{intent}
Reply with one JSON object and nothing else: {{"layers": [layer, ...], "explanation": "<one short sentence>"}}. Leave "id" and "text" empty.

EXAMPLES
{shots}

Request: {text}
"""


# ---- the answer
_BY = re.compile(r"^[\w-]+$")
_COLORS = {"type", "layer", "depth", "status", "area", "degree", "evidence", "score", "none", "format", "recency", "added", "support",
           "community", "component"}
_SIZES = {"connections", "in", "out", "uniform", "tier", "evidence", "score", "gap", "logdeg"}
_WIDTHS = {"thin", "normal", "thick"}


def _normalize(raw, n_from=1):
    """What a model leaves out or spells loosely, filled the way the line parser does: ids, chip text, subgraph, and a
    style value that is not a known word becomes {"by": value}. Anything else is left for the validator to refuse."""
    out = []
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            out.append(d)
            continue
        d = dict(d)
        d["id"] = str(d.get("id") or f"llm-{n_from + i}")
        d.setdefault("text", "")
        d.setdefault("subgraph", {})
        st = d.get("style")
        if isinstance(st, dict):
            st = dict(st)
            for prop, known in (("color", _COLORS), ("size", _SIZES), ("width", _WIDTHS)):
                v = st.get(prop)
                if isinstance(v, str) and v not in known and _BY.match(v):
                    st[prop] = {"by": v}
            d["style"] = st
        out.append(d)
    return out


_LAYERS = TypeAdapter(list[Layer])


def parse_answer(text):
    """The model's reply → (layers, explanation); LayersError (422) with the reason and the raw text when it is not usable."""
    shown = re.sub(r"\s+", " ", text or "").strip()[:300]
    data = llm.json_object(text)
    if data is None or not isinstance(data.get("layers"), list):
        raise LayersError(f'the reply was not a JSON object {{"layers": [...]}} (answer: {shown})')
    if not data["layers"]:
        raise LayersError(f"the reply has no layers (answer: {shown})")
    try:
        layers = _LAYERS.validate_python(_normalize(data["layers"]))
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise LayersError(f"the reply is not a valid list of layers: {where}: {first['msg']} (answer: {shown})") from None
    ex = data.get("explanation")
    return layers, ex.strip() if isinstance(ex, str) else ""


# ---- print: a layer as one line of the language (the Python twin of print() in grammar.ts)
def _quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _of(of):
    return "favorites" if of == "$favorites" else "this" if of == "$focus" else _quote(of)


def _node(c):
    t = c.t
    if t == "all":
        return "all"
    if t == "type":
        return "type " + (" or ".join(c.value) if isinstance(c.value, list) else c.value)
    if t == "degree":
        return f"degree {c.op} {c.n}"
    if t == "hops":
        return f"within {c.n} hop{'' if c.n == 1 else 's'} of {_of(c.of)}"
    if t == "paths":
        return f"paths between {_quote(c.a)} and {_quote(c.b)} up to {c.n} hops"
    if t == "shortest":
        return f"{'all shortest paths' if c.all else 'shortest path'} between {_quote(c.a)} and {_quote(c.b)}"
    if t == "common":
        return f"common neighbours of {_quote(c.a)} and {_quote(c.b)}"
    if t == "component":
        if c.of:
            return f"component of {_quote(c.of)}"
        return "largest component" if not c.rank or c.rank == 1 else f"component {c.rank}"
    if t == "clique":
        return f"clique >= {c.min}"
    if t == "core":
        return f"core {c.k}"
    if t == "cut":
        return "cut vertex"
    if t == "bridge":
        return "bridge end"
    if t == "top":
        return f"top {c.n} by {c.by}"
    if t == "community":
        if c.of:
            return f"community of {_quote(c.of)}"
        return "largest community" if not c.rank or c.rank == 1 else f"community {c.rank}"
    if t == "hasEdge":
        return f"having edge {c.type}" + (" exists = false" if c.exists is False else "")
    if t == "linkedFromType":
        return f"linked_from type {c.type}"
    if t == "createdWithin":
        return f"created > {c.days}d"
    if t == "inArea":
        return f"in area {_quote(c.area)}"
    if t == "about":
        return f"about {_quote(c.phrase)}"
    if t == "favorite":
        return "favorite"
    if t == "mentionedIn":
        return f"mentioned_in chat {_quote(c.chat)}"
    if t == "text":
        return f"text {_quote(c.phrase)}"
    if t == "name":
        return "name " + " or ".join(_quote(s) for s in c.slugs)
    return "not " + _node(c.cond)


def _edge(c):
    t = c.t
    if t == "all":
        return "all"
    if t == "type":
        return f"type {c.value}"
    if t == "count":
        return f"count {c.op} {c.n}"
    if t == "direction":
        return f"direction {c.value}"
    return "between " + " and ".join(_quote(s) for s in c.slugs)


def _word(v):
    return v if isinstance(v, str) else getattr(v, "by", "")


def print_layer(layer):
    conds = " and ".join((_node if layer.target == "nodes" else _edge)(c)
                         for c in ((layer.subgraph.nodes if layer.target == "nodes" else layer.subgraph.edges) or ()))
    if layer.kind != "style":
        grow = f"expand {layer.expand}" if layer.target == "nodes" and layer.expand else ""
        return " ".join(p for p in (layer.kind, layer.target, conds, grow) if p)
    s = layer.style
    prop = next((p for p in ("color", "size", "width", "label") if s is not None and getattr(s, p) is not None), "color")
    value = _word(getattr(s, prop)) if s is not None and getattr(s, prop) is not None else ""
    return " ".join(p for p in (f"style {layer.target} {prop} by {value}", conds and f"for {conds}") if p)


# ---- vocabulary check: the model may name a type the kb does not have
def _warnings(layers, vocab):
    types, kinds, areas = (set(vocab.get(k) or ()) for k in ("node_types", "edge_types", "areas"))
    out = []

    def check(c):
        if c.t == "type" and types:
            for v in c.value if isinstance(c.value, list) else [c.value]:
                if v not in types:
                    out.append(f'no page type "{v}" here (types: {", ".join(sorted(types))})')
        elif c.t == "inArea" and areas and c.area not in areas:
            out.append(f'no area "{c.area}" here')
        elif c.t == "hasEdge" and kinds and c.type.lower() not in kinds:
            out.append(f'no link type "{c.type}" here (types: {", ".join(sorted(kinds))})')
        elif c.t == "not":
            check(c.cond)

    for layer in layers:
        if layer.target == "nodes":
            for c in layer.subgraph.nodes or ():
                check(c)
        else:
            for c in layer.subgraph.edges or ():
                if c.t == "type" and kinds and c.value.lower() not in kinds:
                    out.append(f'no link type "{c.value}" here (types: {", ".join(sorted(kinds))})')
    return list(dict.fromkeys(out))


def _ask(prompt, backend, fallback):
    batch = backend == "batch"
    try:
        res = llm.ask(prompt, backend=backend, fallback=fallback, model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS,
                      id="layers", run_kw={"wait_s": BATCH_WAIT_S, "poll_every": BATCH_POLL_S} if batch else None)
    except llm.LLMError as e:
        raise LayersError(str(e), status=400) from None
    except (llm.HTTPFail, OSError) as e:                # batch talks to the API outside Result.error
        raise LayersError(f"the {backend} backend failed: {e}", status=502) from None
    if res.error and not res.text:
        raise LayersError(f"the {res.backend or backend} backend failed: {res.error}", status=502)
    return res


def translate(text, *, vocabulary, backend=None, fallback=None, op="replace"):
    """Free text → {layers, lines, explanation, backend, fallback_from, usd, warnings}. `vocabulary` is `vocabulary()`'s
    dict (passed in so a caller and a test control it). `fallback` None = "api" when the first backend is the
    subscription, "none" = no fallback. Raises LayersError (`.status`)."""
    text = (text or "").strip()
    if not text:
        raise LayersError("empty request: describe the view, e.g. `only papers within 2 hops of Attention`")
    try:
        b = llm.resolve_backend(backend)
        fb = None if fallback == "none" else (fallback or (DEFAULT_FALLBACK if b == "subscription" else None))
        if fb:
            llm.resolve_backend(fb)
    except llm.LLMError as e:
        raise LayersError(str(e), status=400) from None
    res = _ask(build_prompt(text, vocabulary, op), b, fb)
    layers, explanation = parse_answer(res.text)
    return {"layers": layers, "lines": [print_layer(layer) for layer in layers], "explanation": explanation,
            "backend": getattr(res, "backend_used", "") or res.backend or b,
            "fallback_from": getattr(res, "fallback_from", "") or None, "usd": round(res.usd or 0.0, 6),
            "warnings": _warnings(layers, vocabulary)}
