"""Embedding health and a first semantic map (0 LLM): is the card vector store there and up to date, which pages
sit suspiciously close together, and how the pages group by meaning.

Everything is computed from `kb_distillery.search.vectors` (one unit vector per page card) with numpy only:
spherical k-means with k picked by silhouette, and PCA for the map axes, the variance spectrum and what each
principal component separates. The heavy part is reused
while the store file is unchanged; freshness is read on every call."""
import os

import numpy as np

from kb_distillery.search import vectors

DUPLICATE_COSINE = 0.97      # two different pages this close usually share a boilerplate summary, or are one page twice
DUPLICATES_MAX = 40
K_CANDIDATES = (4, 6, 8, 10)       # at most the 10 colours of the area palette, so one colour is one cluster
MIN_PER_CLUSTER = 8          # k never exceeds pages / this
SILHOUETTE_SAMPLE = 800
CENTRAL = 3                  # pages named per cluster, closest to its centre first
AXES = 8                     # principal components the map can use as an axis
SPECTRUM = 20                # components in the variance chart
ENDS = 4                     # pages named at each end of a component
BIN = 0.025                  # width of a bar in the pair-similarity histogram
PAIR_ROWS_MAX = 3000         # above this many pages the pair statistics use a random sample of pages (4.5M pairs)
PAIRS_MAX = 20               # example pairs per request
PERCENTILES = (1, 5, 25, 50, 75, 95, 99)
SEED = 0


EMPTY_MAP = {"k": 0, "silhouette": 0.0, "clusters": [], "points": [], "duplicates": [],
             "spectrum": [], "effective_dim": 0.0, "mean_cosine": 0.0, "components": [], "similarity": None}


def _titles(cards_dir):
    """{slug: title} from the cards' first line (`# <title>`)."""
    out = {}
    if not os.path.isdir(cards_dir):
        return out
    for f in os.listdir(cards_dir):
        if not f.endswith(".md"):
            continue
        with open(os.path.join(cards_dir, f), encoding="utf-8") as fh:
            first = fh.readline().strip()
        out[f[:-3]] = first[2:].strip() if first.startswith("# ") else f[:-3]
    return out


def _dot(a, b):
    """a @ b without the spurious float32 matmul warnings Accelerate raises on macOS."""
    with np.errstate(all="ignore"):
        return a @ b


def _unit(m):
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1, n)


def kmeans(m, k, iters=30, seed=SEED):
    """Spherical k-means over unit rows → (labels, unit centres). Deterministic: k-means++ start from `seed`."""
    rng = np.random.RandomState(seed)
    n = len(m)
    centres = [m[rng.randint(n)]]
    for _ in range(1, k):
        d = np.clip(1 - np.max(_dot(m, np.stack(centres).T), axis=1), 0, None) ** 2
        total = d.sum()
        centres.append(m[rng.choice(n, p=d / total) if total > 0 else rng.randint(n)])
    c = np.stack(centres)
    labels = np.full(n, -1)
    for _ in range(iters):
        new = np.argmax(_dot(m, c.T), axis=1)
        if np.array_equal(new, labels):
            break
        labels = new
        for j in range(k):
            members = m[labels == j]
            if len(members):
                c[j] = members.sum(axis=0)
        c = _unit(c)
    return labels, c


def silhouette(m, labels, sample=SILHOUETTE_SAMPLE, seed=SEED):
    """Mean silhouette on cosine distance (over at most `sample` rows); 0.0 when fewer than two clusters hold rows."""
    if len(m) > sample:
        pick = np.random.RandomState(seed).choice(len(m), sample, replace=False)
        m, labels = m[pick], labels[pick]
    ids = [j for j in np.unique(labels)]
    if len(ids) < 2:
        return 0.0
    dist = 1 - _dot(m, m.T).astype(np.float64)
    sums = np.stack([dist[:, labels == j].sum(axis=1) for j in ids], axis=1)
    sizes = np.array([(labels == j).sum() for j in ids])
    own = np.searchsorted(ids, labels)
    rows = np.arange(len(m))
    own_n = sizes[own]
    a = sums[rows, own] / np.maximum(own_n - 1, 1)
    other = sums / sizes
    other[rows, own] = np.inf
    b = other.min(axis=1)
    s = np.where(own_n > 1, (b - a) / np.maximum(np.maximum(a, b), 1e-12), 0.0)
    return float(s.mean())


def cluster(m):
    """(labels, centres, silhouette) with k picked by silhouette; one cluster when there are too few pages to split."""
    n = len(m)
    ks = [k for k in K_CANDIDATES if k * MIN_PER_CLUSTER <= n]
    if not ks:
        centre = _unit(m.sum(axis=0, keepdims=True)) if n else np.zeros((0, m.shape[1] if m.ndim == 2 else 0))
        return np.zeros(n, dtype=int), centre, 0.0
    best = None
    for k in ks:
        labels, centres = kmeans(m, k)
        score = silhouette(m, labels)
        if best is None or score > best[2]:
            best = (labels, centres, score)
    return best


def pca(m, axes=AXES, spectrum=SPECTRUM):
    """Principal components of the rows → (coords, ratios, effective): `coords` is rows × min(axes, rank) scaled to
    [0, 1] per component, `ratios` the share of variance of the first `spectrum` components, `effective` the
    participation ratio (how many directions the variance is really spread over). The sign of a component is fixed
    (its largest loading is positive), so the same store always draws the same map."""
    if len(m) < 2:
        return np.full((len(m), 0), 0.5), [], 0.0
    x = (m - m.mean(axis=0)).astype(np.float64)
    _u, sv, vt = np.linalg.svd(x, full_matrices=False)
    var = sv ** 2
    total = var.sum()
    if total <= 1e-10 * len(m):          # unit rows that are all the same: what is left is rounding noise
        return np.full((len(m), 0), 0.5), [], 0.0
    rank = int((var > total * 1e-12).sum())
    keep = min(axes, rank)
    comps = vt[:keep]
    comps = comps * np.where(comps[np.arange(keep), np.abs(comps).argmax(axis=1)] < 0, -1, 1)[:, None]
    p = _dot(x, comps.T)
    lo, hi = p.min(axis=0), p.max(axis=0)
    coords = (p - lo) / np.where(hi - lo == 0, 1, hi - lo)
    return coords, [float(v) for v in (var / total)[:min(spectrum, rank)]], float(total ** 2 / (var ** 2).sum())


def duplicates(m, slugs, threshold=DUPLICATE_COSINE, limit=DUPLICATES_MAX):
    """[(a, b, cosine)] of the page pairs at or above `threshold`, closest first."""
    found = []
    for start in range(0, len(m), 512):
        sims = _dot(m[start:start + 512], m.T)
        for i, j in zip(*np.where(sims >= threshold)):
            if start + i < j:
                found.append((slugs[start + i], slugs[j], float(sims[i, j])))
    found.sort(key=lambda t: (-t[2], t[0], t[1]))
    return found[:limit]


def _pair_rows(m, seed=SEED):
    """(rows, sampled): every row, or a random PAIR_ROWS_MAX of them when all pairs would be too many."""
    if len(m) <= PAIR_ROWS_MAX:
        return np.arange(len(m)), False
    return np.sort(np.random.RandomState(seed).choice(len(m), PAIR_ROWS_MAX, replace=False)), True


def _square(m, rows):
    """The cosine of every row of `rows` with every other, in float64 (the histogram and the pair sampler must put a
    cosine near a bar's edge in the same bar); a broken vector (NaN) counts as unrelated."""
    sub = m[rows].astype(np.float64)
    return np.clip(np.nan_to_num(_dot(sub, sub.T)), -1, 1)


def similarity(m):
    """How similar two pages are, over every pair: a histogram in BIN-wide bars, the same for each page's nearest
    neighbour, and the percentiles of both. None with fewer than two pages. Exact up to PAIR_ROWS_MAX pages (about
    4.5 million pairs); beyond that it is measured on a random sample of pages and says so (`sampled`)."""
    if len(m) < 2:
        return None
    rows, sampled = _pair_rows(m)
    sims = _square(m, rows)
    pairs = sims[np.triu_indices(len(rows), k=1)]
    np.fill_diagonal(sims, -np.inf)
    nearest = sims.max(axis=1)
    lo = float(np.floor(pairs.min() / BIN) * BIN)
    n_bins = max(1, int(round((1.0 - lo) / BIN)))
    edges = [round(lo + i * BIN, 3) for i in range(n_bins + 1)]
    edges[-1] = 1.0
    cut = np.array(edges)
    cut[-1] = 1.0 + 1e-6                 # a cosine of exactly 1 belongs to the last bar
    pct = lambda a: {f"p{p}": round(float(np.percentile(a, p)), 3) for p in PERCENTILES}     # noqa: E731
    return {"edges": edges, "counts": [int(c) for c in np.histogram(pairs, bins=cut)[0]],
            "nearest": [int(c) for c in np.histogram(nearest, bins=cut)[0]], "pairs": int(len(pairs)),
            "pages": int(len(rows)), "sampled": sampled, "percentiles": pct(pairs), "nearest_percentiles": pct(nearest)}


def sample_pairs(lo, hi, n=8, seed=0, db_path=None, cards_dir=None):
    """Random page pairs whose cosine is in [lo, hi) → {"count": pairs in the range, "pairs": [{a, b, cosine}]},
    closest first. `seed` picks which ones, so the same request shows the same pairs and the next seed shows others.
    Counted over the same pages as `similarity` (all of them up to PAIR_ROWS_MAX)."""
    db_path, cards_dir = db_path or vectors.DB_PATH, cards_dir or vectors.CARDS_DIR
    n = max(1, min(int(n), PAIRS_MAX))
    empty = {"count": 0, "pairs": []}
    if not os.path.exists(db_path):
        return empty
    try:
        v = vectors.load(db_path)
    except ValueError:
        return empty
    if v is None or len(v) < 2:
        return empty
    rows, _sampled = _pair_rows(v.m)
    sims = _square(v.m, rows)
    hi = hi + 1e-6 if hi >= 1.0 else hi
    inside = sims >= lo
    inside &= sims < hi
    ii, jj = np.where(np.triu(inside, k=1))
    if not len(ii):
        return empty
    pick = np.random.RandomState(int(seed) % (2 ** 31)).choice(len(ii), min(n, len(ii)), replace=False)
    titles = _titles(cards_dir)
    ref = lambda i: {"slug": v.slugs[rows[i]], "title": titles.get(v.slugs[rows[i]], v.slugs[rows[i]])}     # noqa: E731
    found = sorted(({"a": ref(ii[k]), "b": ref(jj[k]), "cosine": round(float(sims[ii[k], jj[k]]), 3)} for k in pick),
                   key=lambda d: -d["cosine"])
    return {"count": int(len(ii)), "pairs": found}


def _titled(value, titles):
    """A copy of `value` where every {"slug": s, ...} also carries its page title (the slug when it has no card)."""
    if isinstance(value, list):
        return [_titled(x, titles) for x in value]
    if isinstance(value, dict):
        out = {k: _titled(x, titles) for k, x in value.items()}
        if "slug" in out:
            out["title"] = titles.get(out["slug"], out["slug"])
        return out
    return value


def _map(v):
    """The part that depends on the vectors alone (pages by slug, no titles): clusters, map points, components
    and near-duplicates."""
    ref = lambda s: {"slug": s}     # noqa: E731
    if not len(v):
        return {**EMPTY_MAP}
    labels, centres, score = cluster(v.m)
    order = sorted(set(labels.tolist()), key=lambda j: (-int((labels == j).sum()), j))    # largest first
    rank = {j: i for i, j in enumerate(order)}
    clusters = []
    for j in order:
        idx = np.where(labels == j)[0]
        closeness = _dot(v.m[idx], centres[j])
        top = idx[np.argsort(-closeness)[:CENTRAL]]
        clusters.append({"id": rank[j], "size": int(len(idx)), "cohesion": round(float(closeness.mean()), 3),
                         "central": [ref(v.slugs[i]) for i in top]})
    coords, ratios, effective = pca(v.m)
    points = [{**ref(s), "x": round(float(coords[i, 0]), 4) if coords.shape[1] else 0.5,
               "y": round(float(coords[i, 1]), 4) if coords.shape[1] > 1 else 0.5,
               "pc": [round(float(c), 4) for c in coords[i]], "cluster": rank[int(labels[i])]}
              for i, s in enumerate(v.slugs)]
    components = []
    for a in range(coords.shape[1]):
        by = np.argsort(coords[:, a])
        components.append({"index": a, "variance": round(ratios[a], 4), "cumulative": round(sum(ratios[:a + 1]), 4),
                           "low": [ref(v.slugs[i]) for i in by[:ENDS]], "high": [ref(v.slugs[i]) for i in by[::-1][:ENDS]]})
    centre = v.m.mean(axis=0)
    spread = {"spectrum": [round(r, 4) for r in ratios], "effective_dim": round(effective, 1),
              "mean_cosine": round(float(centre @ centre), 3), "components": components}
    dups = [{"a": ref(a), "b": ref(b), "cosine": round(c, 3)} for a, b, c in duplicates(v.m, v.slugs)]
    return {"k": len(clusters), "silhouette": round(score, 3), "clusters": clusters, "points": points, "duplicates": dups, **spread,
            "similarity": similarity(v.m)}


def build_embedding_report(db_path=None, cards_dir=None):
    """The Embedding tab's data: store status, pages behind, near-duplicates, clusters and map points."""
    db_path, cards_dir = db_path or vectors.DB_PATH, cards_dir or vectors.CARDS_DIR
    ok, line = vectors.status(db_path, cards_dir)
    fresh = vectors.freshness(db_path, cards_dir)
    base = {"built": fresh is not None, "ok": ok, "line": line, "model": None, "dim": 0, "cards": 0, "vectors": 0,
            "missing": [], "changed": [], "removed": [], "duplicate_cosine": DUPLICATE_COSINE,
            **EMPTY_MAP}
    if fresh is None:
        return base
    titles = _titles(cards_dir)
    ref = lambda s: {"slug": s, "title": titles.get(s, s)}     # noqa: E731
    base.update(cards=fresh["cards"], vectors=fresh["vectors"],
                **{k: [ref(s) for s in fresh[k]] for k in ("missing", "changed", "removed")})
    from kb_distillery.graph import cache
    st = os.stat(db_path)                # before the load: a store rewritten in between is rebuilt on the next call
    try:
        v = vectors.load(db_path)
    except ValueError as e:              # a half-rebuilt store (mixed models): report it, draw nothing
        return {**base, "ok": False, "line": str(e)}
    if v is None or not len(v):
        return base
    v.m = np.nan_to_num(v.m)             # a broken vector (NaN) becomes a zero vector: unrelated to everything
    heavy = cache.memo("embedding:" + db_path, lambda: (st.st_mtime_ns, st.st_size), lambda: _map(v))
    return {**base, "model": v.model, "dim": int(v.m.shape[1]), **_titled(heavy, titles)}
