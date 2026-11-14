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
<op> is one of >= <= > < =. Names are page titles or slugs, quoted. Style values: color by type|layer|depth|status|area|
degree|evidence|score|none; size by connections|in|out|uniform|tier|evidence|score|gap|logdeg; width by thin|normal|thick;
any other value is a page property written {"by": "<property>"}."""

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


def build_prompt(text, vocab, op="replace"):
    shots = "\n\n".join(f"Request: {q}\n" + json.dumps({"layers": ls, "explanation": ""}) for q, ls in EXAMPLES)
    titles = "; ".join(vocab.get("titles") or ()) or "none"
    intent = {"replace": "The layers replace the current view's show/hide layers.",
              "stack": "The layers are added on top of the current view.",
              "remove": "The request names a layer to take away: answer the layer it describes."}[op]
    return f"""You turn a request about a knowledge-base graph into layer objects: each layer shows pages or links, hides them, or styles them. Answer layers, never Cypher.

QUERY LANGUAGE (one line per layer; every line is one layer)
{GRAMMAR}

LAYER OBJECTS
{SHAPES}

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
_COLORS = {"type", "layer", "depth", "status", "area", "degree", "evidence", "score", "none", "format", "recency", "added"}
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
        return f"within {c.n} hops of {_of(c.of)}"
    if t == "paths":
        return f"paths between {_quote(c.a)} and {_quote(c.b)} up to {c.n} hops"
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
        return " ".join(p for p in (layer.kind, layer.target, conds) if p)
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
