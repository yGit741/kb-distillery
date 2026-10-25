"""What a share build adds for the app's Home screen, plus `strip_my_notes`, the cut `build.apply_profile`
makes to every public page.

Home cards and the guided tour are set per build in `share.toml`:

    [home]
    tour = "thesis-story"     # a tour name from frontend/src/features/home/tours.ts, or omit for none
    [[home.cards]]
    title = "Boolean analysis"
    pages = ["theme-boolean-analysis", "fourier-analysis-of-boolean-functions"]
    focus = "theme-boolean-analysis"
    caption = "Where my reading on Fourier analysis of Boolean functions sits."

They land in the kb-data blob as `home = {cards, tour[, view]}` (`view` from `share … --view <id>`:
the graph view the app opens on when the URL carries no `?view=`; the Home "Open in full graph" links carry it). A card keeps only pages present in the build
(after the public cuts), and is dropped when none are left, so Home never opens on an empty card.
"""
import re
import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "share.toml"

# `## My notes` (the user's own section, see core/wikiio.py) up to the next h1/h2 heading or the end
MY_NOTES = re.compile(r"^##[ \t]+My notes\b.*?(?=^#{1,2}[ \t]|\Z)", re.M | re.S)


def load_home(path: Path = CONFIG_PATH) -> dict:
    """`[home]` of share.toml as {cards: [...], tour: str|None}; a missing or broken file means none."""
    try:
        home = tomllib.loads(path.read_text(encoding="utf-8")).get("home") or {}
    except (OSError, tomllib.TOMLDecodeError):
        home = {}
    cards = [c for c in home.get("cards") or [] if isinstance(c, dict) and c.get("title") and c.get("pages")]
    tour = home.get("tour") if isinstance(home.get("tour"), str) and home.get("tour") else None
    return {"cards": cards, "tour": tour}


def strip_my_notes(markdown: str) -> str:
    """The page without its `## My notes` section (public builds publish the synthesis, not the notes).
    A page without one comes back byte-identical."""
    if not markdown or not MY_NOTES.search(markdown):
        return markdown
    return MY_NOTES.sub("", markdown).rstrip() + "\n"


def apply_home(data: dict, home: dict, view=None) -> dict:
    """Add `home` to the blob (after `apply_profile`, so cards only name pages the build kept).
    `view` (`share … --view <id>`) is the graph view the app opens on when the URL names none."""
    present = {n["id"] for n in data["graph"]["nodes"]}
    cards = []
    for c in home.get("cards", []):
        pages = [s for s in c["pages"] if s in present]
        if not pages:
            continue
        card = {"title": c["title"], "pages": pages}
        if c.get("focus") in present:
            card["focus"] = c["focus"]
        if c.get("caption"):
            card["caption"] = c["caption"]
        cards.append(card)
    data["home"] = {"cards": cards, "tour": home.get("tour")}
    if view:
        data["home"]["view"] = view
    return data
