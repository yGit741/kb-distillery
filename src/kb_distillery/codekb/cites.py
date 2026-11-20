"""Fact citations in wiki pages: placeholders, check, and the check of what is already cited.

A wiki page cites a code fact with a placeholder right after the claim:

    {{ir-core-py-src:Fb1d14}}          one fact (links the row's last anchor)
    {{ir-core-py-src:Fb1d14,F584f4}}   several facts of one card
    {{ir-core-py-src:Fb1d14@0+1}}      pick anchors of the row by index (Fid:0+1 per fact)

and a cited fact reads ``(`Fb1d14` [file.py:7](<permalink>))[^ir-core-py-src]``. The card in raw/printed-docs/ is the evidence.

    distill code cite --check [page ...]      what the placeholders would expand to, and which cannot (writes nothing)
    distill code cite --check --refresh       what re-pointing cited facts at the current export would change
    distill code check-cites                  every cited fact still exists in its card, links are that fact's anchors

Writing the expansion into a page is not shipped yet: a page change is a knowledge step (`distill ops begin` ... `commit`), and
this tool does not yet know the page's `raw:` / `## Sources` form. Until then a person (or an agent inside an ops session) pastes
the expansion that `cite --check` prints.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

CARD_DIR = "raw/printed-docs"
FID = r"F[0-9a-f]{5}x*"
ROW = re.compile(rf"^\| ({FID}) \|(.*)$", re.M)
URL = re.compile(r"\]\((https?://[^)\s]+)\)")
_ONE = rf"{FID}(?::[0-9]+(?:\+[0-9]+)*)?"
PH = re.compile(r"\{\{([a-z0-9-]+):(" + _ONE + r"(?:\s*,\s*" + _ONE + r")*)(?:@([0-9]+(?:\+[0-9]+)*))?\}\}")
_LINKS = r"(?:\s*\[[^\]\n]*\]\([^)\s]+\))*"
CITE = re.compile(r"\(((?:`" + FID + r"`" + _LINKS + r"(?:\s*·\s*)?)+)\)\[\^(ir-[a-z0-9-]+)\]")
FACT_IN_CITE = re.compile(rf"`({FID})`((?:\s*\[[^\]\n]*\]\([^)\s]+\))*)")
LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]+)\)")
NOT_PAGES = ("index.md", "log.md")


# ---------------------------------------------------------------------------------------------------- cards in raw/
class Card:
    def __init__(self, path: Path):
        text = path.read_text(encoding="utf-8")
        self.slug, self.path = path.stem, path
        end = text.find("\n---", 4)
        if end < 0:
            end = len(text)
        fm = text[4:end]
        m = re.search(r'^title: "?(.*?)"?$', fm, re.M)
        self.title = (m.group(1) if m else self.slug).removeprefix("IR: ")
        self.pinned = dict(re.findall(r'^  ([A-Za-z0-9._-]+): "([0-9a-f]{40})"', fm, re.M))
        self.facts = {fid: URL.findall(rest) for fid, rest in ROW.findall(text[end:])}

    def footnote(self) -> str:
        pins = ", ".join(f"{r}@{s[:8]}" for r, s in sorted(self.pinned.items()))
        return f"Code IR: {self.title} (facts read from the code by a parser at {pins})"


def load_cards(kb: Path) -> dict[str, Card]:
    return {p.stem: Card(p) for p in sorted((kb / CARD_DIR).glob("ir-*.md"))}


def _file_of(url: str) -> str:
    """The repository path of an anchor: after `/blob/<sha>/` (GitHub, GitLab), else the address without its fragment."""
    m = re.search(r"/(?:blob|tree)/[0-9a-f]{7,40}/([^#]+)", url)
    return m.group(1) if m else url.split("#", 1)[0]


def anchor_label(url: str) -> str:
    line = re.search(r"#L(\d+)", url)
    name = _file_of(url).rstrip("/").rsplit("/", 1)[-1] or "code"
    return f"{name}:{line.group(1)}" if line else name


def _pages(kb: Path, pages: list[str] | None = None) -> list[Path]:
    wiki = kb / "wiki"
    if pages:
        names = [p.removesuffix(".md") for p in pages]
        if any("/" in n or ".." in n or "\\" in n for n in names):
            raise SystemExit("pages are slugs of wiki/ (no folders)")
        return [wiki / f"{n}.md" for n in names]
    return [p for p in sorted(wiki.glob("*.md")) if p.name not in NOT_PAGES]


# ---------------------------------------------------------------------------------------------------- expand
def _resolve(cards: dict[str, Card], name: str) -> str | None:
    return name if name in cards else f"ir-{name}" if f"ir-{name}" in cards else None


def _expand(body: str, cards: dict[str, Card], errors: list[str], used: set[str]) -> str:
    def one(m: re.Match) -> str:
        slug = _resolve(cards, m.group(1))
        if not slug:
            errors.append(f"unknown card in {m.group(0)} (cards live in {CARD_DIR}/: run `distill code export` first)")
            return m.group(0)
        c = cards[slug]
        allpick = [int(x) for x in m.group(3).split("+")] if m.group(3) else None
        parts = []
        for item in (x.strip() for x in m.group(2).split(",")):
            fid, _, own = item.partition(":")
            pick = [int(x) for x in own.split("+")] if own else allpick
            if fid not in c.facts:
                errors.append(f"fact {fid} not in {slug}")
                return m.group(0)
            a = c.facts[fid]
            chosen = [a[k] for k in pick if k < len(a)] if pick else a[-1:]
            if pick and len(chosen) < len(pick):
                errors.append(f"anchor index out of range in {m.group(0)} ({len(a)} anchors)")
            parts.append(f"`{fid}`" + "".join(f" [{anchor_label(u)}]({u})" for u in chosen))
        used.add(slug)
        return f"({' · '.join(parts)})[^{slug}]"

    return PH.sub(one, body)


def _refresh(body: str, cards: dict[str, Card], errors: list[str], used: set[str]) -> str:
    """Re-point the links of every cited fact at the fact's current anchors (same files where possible)."""
    def group(m: re.Match) -> str:
        slug = m.group(2)
        if slug not in cards:
            errors.append(f"card {slug} is not in {CARD_DIR}/")
            return m.group(0)
        c, parts = cards[slug], []
        for fm in FACT_IN_CITE.finditer(m.group(1)):
            fid, old = fm.group(1), [u for _, u in LINK.findall(fm.group(2))]
            if fid not in c.facts:
                errors.append(f"fact {fid} is gone from {slug}: re-read the card and revise the claim")
                return m.group(0)
            a = c.facts[fid]
            new = [next((u for u in a if _file_of(u) == _file_of(o)), a[-1] if a else o) for o in old] if old else []
            parts.append(f"`{fid}`" + "".join(f" [{anchor_label(u)}]({u})" for u in dict.fromkeys(new)))
        used.add(slug)
        return f"({' · '.join(parts)})[^{slug}]"

    return CITE.sub(group, body)


def cite(kb: Path, pages: list[str], check: bool = False, refresh: bool = False) -> int:
    """Report what expanding the placeholders (or refreshing the cited facts) of the pages would change. Exit 1 when a page has
    an error, 2 when asked to write."""
    if not check:
        print("cite writes nothing yet: run it with --check and paste the expansion inside an ops session (see `distill code cite --help`)")
        return 2
    cards = load_cards(kb)
    paths = _pages(kb, pages)
    bad = changed = 0
    for p in paths:
        if not p.is_file():
            print(f"FAIL {p.stem}\n     no such page")
            bad += 1
            continue
        text = p.read_text(encoding="utf-8")
        errors: list[str] = []
        used: set[str] = set()
        body = (_refresh if refresh else _expand)(text, cards, errors, used)
        if not refresh and PH.search(body) is None and re.search(r"\{\{[a-z0-9-]+:F", body):
            errors.append("malformed placeholder: " + re.search(r"\{\{[^}\n]*\}\}?", body).group(0))
        if errors:
            bad += 1
            print(f"FAIL {p.stem}")
            for e in errors:
                print(f"     {e}")
        if body != text:
            changed += 1
            print(f"would change {p.stem}")
            for old in (CITE if refresh else PH).finditer(text):
                new = (_refresh if refresh else _expand)(old.group(0), cards, [], set())
                if new != old.group(0):
                    print(f"     {old.group(0)}\n  -> {new}")
            for s in sorted(used):
                if not re.search(rf"^\[\^{re.escape(s)}\]:", body, re.M):
                    print(f"     footnote to add: [^{s}]: {cards[s].footnote()}")
    print(f"{len(paths)} pages, {changed} would change, {bad} with errors")
    return 1 if bad else 0


# ---------------------------------------------------------------------------------------------------- check
def check_cites(kb: Path) -> int:
    """Every cited fact exists in its card (a fact id changes when the fact changes), and every link next to it is one of that
    fact's anchors (a link from an older export: run `cite --check --refresh`)."""
    cards = load_cards(kb)
    cited: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    bad = 0
    pages = _pages(kb)
    for p in pages:
        body = p.read_text(encoding="utf-8")
        errs, warns = [], []
        for left in re.findall(r"\{\{[a-z0-9-]+:F[^}\n]*\}\}", body):
            errs.append(f"unexpanded placeholder {left} (see `distill code cite --check`)")
        for m in CITE.finditer(body):
            slug = m.group(2)
            if slug not in cards:
                errs.append(f"card {slug} is not in {CARD_DIR}/")
                continue
            c = cards[slug]
            for fm in FACT_IN_CITE.finditer(m.group(1)):
                fid = fm.group(1)
                if fid not in c.facts:
                    errs.append(f"fact {fid} is gone from {slug}: the code changed; re-read the card and revise the claim")
                    continue
                cited[slug][p.stem].add(fid)
                for _, u in LINK.findall(fm.group(2)):
                    if u not in c.facts[fid]:
                        same_file = any(_file_of(u) == _file_of(a) for a in c.facts[fid])
                        (warns if same_file else errs).append(
                            f"{fid}: link {anchor_label(u)} is {'from an older export (run `cite --check --refresh`)' if same_file else 'not an anchor of this fact'}")
        for s in set(re.findall(r"\[\^(ir-[a-z0-9-]+)\]", body)) - set(cards):
            errs.append(f"footnote [^{s}] names a card that is not in {CARD_DIR}/")
        if errs or warns:
            print(f"{'FAIL' if errs else 'warn'} {p.stem}")
            for e in errs:
                print(f"     ERROR {e}")
            for w in warns:
                print(f"     warn  {w}")
        bad += bool(errs)
    print(f"{len(pages)} pages, {bad} with errors")
    if cards:
        print("card                                         facts  cited  pages")
        for slug, c in cards.items():
            ids = set().union(*cited[slug].values()) if cited.get(slug) else set()
            print(f"  {slug:42s} {len(c.facts):5d} {len(ids):6d} {len(cited.get(slug, {})):6d}")
    return 1 if bad else 0
