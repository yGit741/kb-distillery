"""Free text → a graph view spec: Cypher for the selection plus a style clause (kb_distillery.graph.shape).

  * text that starts with MATCH is Cypher (optionally followed by `-- <style>` / `style: <style>`): no LLM;
  * text that is a style clause list on its own keeps the current node set (`cypher` is None): no LLM;
  * anything else goes through the shared LLM tool (`kb_distillery.llm`, backend `subscription|api|batch`) with
    the Cypher subset, this kb's labels and edge kinds, the style grammar and a few examples. The reply is
    checked by running the Cypher once; a Cypher or style error is sent back to the model once, then it is a
    422 with the hint.
"""
import json
import re

from kb_distillery import llm
from kb_distillery.graph import query as cypher
from kb_distillery.graph.shape import GRAMMAR, NODE_PROPS, ShapeError, format_style, is_cypher, parse_style, split_cypher

MODEL = "haiku"
EFFORT = "low"
MAX_TOKENS = 1024
BATCH_WAIT_S = 300          # an interactive request does not wait for a batch for hours; it fails with a hint instead
BATCH_POLL_S = 5

# The docstring of kb_distillery.search.cypher says the same to people; this is what the model needs.
CYPHER_SUBSET = """\
Read-only Cypher, one MATCH query. Strings take double quotes. Supported: labels (:Paper, :Idea, :Source, :Concept ...),
typed edges (:MENTIONS, :BOOK, :SHARES_SOURCE), [:A|B], WHERE filters, [*1..3], COUNT/ORDER BY/LIMIT, DISTINCT,
CONTAINS/IN/STARTS WITH. Not supported: NOT patterns, OPTIONAL MATCH, shortestPath, subqueries, WITH/UNION/UNWIND,
undirected patterns (always give an arrow a direction). Every node has the properties """ + ", ".join(NODE_PROPS) + """.
Always RETURN the slug of each node (`p.slug`), never whole nodes."""

EXAMPLES = (
    ("show papers that mention tensor rank, group by source, colour by type",
     'MATCH (p:Paper)-[:MENTIONS]->(i:Idea) WHERE i.slug CONTAINS "tensor-rank" RETURN p.slug, i.slug',
     "group by layer; colour by type",
     "Papers that link to an idea whose slug contains tensor-rank, grouped by layer and coloured by page type."),
    ("ideas from 2023 onward, as a timeline sized by how connected they are",
     "MATCH (i:Idea) WHERE i.year >= 2023 RETURN i.slug",
     "layout timeline; size by degree",
     "Idea pages with year 2023 or later, laid out on a timeline, bigger when they have more links."),
    ("everything within two links of attention, without the similarity edges",
     'MATCH (a:Idea)-[*1..2]->(b) WHERE a.slug = "attention" RETURN DISTINCT b.slug',
     "hide SIMILAR_TO",
     "Pages reachable from attention in one or two directed links; similarity edges are hidden."),
    ("only the sources, in a ring, labelled with their titles",
     "MATCH (s:Source) RETURN s.slug",
     "layout radial; label title",
     "All pages in the source layer, on a radial layout showing each title."),
    ("concepts with graph in the title, coloured by maturity, hide papers",
     'MATCH (c:Concept) WHERE c.title CONTAINS "graph" RETURN c.slug',
     "colour by maturity; hide Paper",
     "Concept pages whose title contains graph, coloured by maturity; paper nodes are hidden."),
)


def vocabulary(graph=None):
    """{labels: {label: count}, edge_kinds: {kind: count}} of the kb's Cypher graph (what `MATCH` can name)."""
    g = cypher.current_graph() if graph is None else graph
    labels, kinds = {}, {}
    for _, d in g.nodes(data=True):
        for lbl in d.get("__labels__") or ():
            labels[lbl] = labels.get(lbl, 0) + 1
    for _, _, d in g.edges(data=True):
        k = d.get("kind")
        if k:
            kinds[k] = kinds.get(k, 0) + 1
    return {"labels": dict(sorted(labels.items())), "edge_kinds": dict(sorted(kinds.items()))}


def _counts(d):
    return ", ".join(f"{k} ({n})" for k, n in d.items()) or "none"


def build_prompt(text, vocab, limit=cypher.MAX_ROWS):
    shots = "\n\n".join(
        f"Request: {q}\n" + json.dumps({"cypher": c, "style_text": s, "explanation": e}, ensure_ascii=False)
        for q, c, s, e in EXAMPLES)
    return f"""You turn a request about a knowledge-base graph into a view: Cypher that selects the nodes, plus style clauses that say how to draw them.

CYPHER
{CYPHER_SUBSET}
The view shows at most {limit} rows; add LIMIT only when the request asks for a top-N.

THIS KNOWLEDGE BASE
Node labels (count): {_counts(vocab["labels"])}
Edge kinds (count): {_counts(vocab["edge_kinds"])}
Use only labels and edge kinds from these lists. The examples below may name others; they only show the shape.

STYLE CLAUSES (style_text; separated by `;`, may be empty)
{GRAMMAR}
`hide` takes a node label (CamelCase, e.g. Paper) or an edge kind (ALL_CAPS, e.g. MENTIONS). Properties: {", ".join(NODE_PROPS)}.
Pick style from the request only; leave style_text empty when it asks for none.

ANSWER
Reply with one JSON object and nothing else: {{"cypher": "...", "style_text": "...", "explanation": "one sentence in plain words"}}

EXAMPLES
{shots}

Request: {text}
"""


def retry_prompt(prompt, reply, error):
    return (f"{prompt}\nYour previous answer was:\n{reply.strip()[:1500]}\n\nIt was rejected: {error}\n"
            "Answer again with the corrected JSON object only.\n")


def _ask(prompt, backend):
    req = llm.Request(prompt=prompt, id="shape", model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS)
    try:
        kw = {"wait_s": BATCH_WAIT_S, "poll_every": BATCH_POLL_S} if backend == "batch" else {}
        res = llm.run([req], backend=backend, **kw)[0]
    except llm.LLMError as e:
        raise ShapeError(str(e), status=400) from None
    except (llm.HTTPFail, OSError) as e:                # batch talks to the API outside Result.error
        raise ShapeError(f"the {backend} backend failed: {e}", status=502) from None
    if res.error and not res.text:
        raise ShapeError(f"the {res.backend or backend} backend failed: {res.error}", status=502)
    return res


def _reply(text):
    """The model's JSON → (cypher, style_text, explanation); ShapeError when it is not usable."""
    data = llm.json_object(text)
    if data is None:
        raise ShapeError('the reply was not a JSON object {"cypher", "style_text", "explanation"}')
    cy, st, ex = (data.get(k) for k in ("cypher", "style_text", "explanation"))
    if not all(v is None or isinstance(v, str) for v in (cy, st, ex)):
        raise ShapeError("cypher, style_text and explanation must be strings")
    cy, st = (cy or "").strip(), (st or "").strip()
    if not cy and not st:
        raise ShapeError("the reply has neither cypher nor style_text")
    return cy, st, (ex or "").strip()


def _select(cy, limit, graph):
    """Run the selection once → its table; a rejected query becomes a ShapeError carrying the engine's hint."""
    try:
        return cypher.run(cy, limit=limit, graph=graph)
    except cypher.QueryError as e:
        raise ShapeError(str(e)) from None


EMPTY_TABLE = {"columns": [], "rows": [], "row_count": 0, "truncated": False}


def _style_warnings(style, graph):
    """Hidden names the kb does not have: they would hide nothing, silently."""
    if not (style.hide_labels or style.hide_edge_kinds):
        return []
    v = vocabulary(cypher.current_graph() if graph is None else graph)
    out = [f"hide: no node label `{n}` (labels: {', '.join(v['labels'])})" for n in style.hide_labels
           if n not in v["labels"]]
    return out + [f"hide: no edge kind `{n}` (kinds: {', '.join(v['edge_kinds'])})" for n in style.hide_edge_kinds
                  if n not in v["edge_kinds"]]


def _result(cy, style, explanation, source, table, warnings, backend=None, usd=None, graph=None):
    warnings = [*warnings, *_style_warnings(style, graph)]
    if cy is not None:
        if table["row_count"] == 0:
            warnings.append("row_count is 0: the query matched nothing")
        if table["truncated"]:
            warnings.append(f"the result was cut at {table['row_count']} rows")
    return {"cypher": cy, "style": style.model_dump(), "style_text": format_style(style),
            "explanation": explanation, "source": source, "warnings": warnings, **table,
            "backend": backend, "usd": usd}


def shape(text, limit=cypher.MAX_ROWS, backend=None, graph=None):
    """Free text → {cypher, style, style_text, explanation, source, warnings, columns, rows, row_count, truncated,
    backend, usd}. `source` is "cypher" when no LLM was needed, else "llm". Raises ShapeError (`.status`)."""
    text = (text or "").strip()
    if not text:
        raise ShapeError("empty request: describe the view, e.g. `papers that mention attention; colour by type`")
    limit = max(1, min(int(limit), cypher.MAX_ROWS))
    if is_cypher(text):
        cy, st = split_cypher(text)
        style = parse_style(st)
        return _result(cy, style, "Cypher as written; no LLM call.", "cypher", _select(cy, limit, graph), [],
                       graph=graph)
    try:
        style = parse_style(text)
    except ShapeError:
        pass
    else:
        return _result(None, style, "Style clauses only: the current node set stays.", "cypher", dict(EMPTY_TABLE), [],
                       graph=graph)

    b = _resolve(backend)
    g = cypher.current_graph() if graph is None else graph
    prompt = build_prompt(text, vocabulary(g), limit)
    usd, last, attempt_text = 0.0, "", ""
    for attempt in range(1 if b == "batch" else 2):      # a retried batch would wait for hours twice
        res = _ask(prompt if attempt == 0 else retry_prompt(prompt, attempt_text, last), b)
        usd += res.usd
        attempt_text = res.text
        try:
            cy, st, ex = _reply(res.text)
            style = parse_style(st)
            table = _select(cy, limit, g) if cy else dict(EMPTY_TABLE)
        except ShapeError as e:
            last = str(e)
            continue
        return _result(cy or None, style, ex, "llm", table, [], backend=res.backend, usd=round(usd, 6), graph=g)
    shown = re.sub(r"\s+", " ", attempt_text).strip()[:300]
    raise ShapeError(f"could not turn that into a valid view: {last} (last answer: {shown})")


def _resolve(backend):
    """Resolve the backend up front so a bad `backend` or $KB_LLM_BACKEND is a 400 before any work."""
    try:
        return llm.resolve_backend(backend)
    except llm.LLMError as e:
        raise ShapeError(str(e), status=400) from None
