"""Page conventions a kit (or a kb) names: the takeaways heading and the focus pages. The ONE accessor.

A kit.toml (and a kb.toml, for a kb's own choice) may carry

    [pages]
    takeaways_heading = "Takeaways"   # the `## <heading>` section where a source page says what it means for the reader
    focus_slugs = []                  # kb-convention pages (e.g. a research statement) kept out of retrieval and orphans

Resolution, first hit wins: the kb.toml's own `[pages]`, then its kit chain from the kit itself up to the root kit,
then the engine defaults below. Engine code reads these through `takeaways_heading()` / `focus_slugs()` and never
spells a value itself, so a kb on the `research` kit keeps its wording and every other kb gets the generic one.
"""
from __future__ import annotations

from kb_distillery.config import kb as kbconfig

TABLE = "pages"
DEFAULTS = {"takeaways_heading": "Takeaways", "focus_slugs": []}
CONVENTION_SLUGS = ("AGENTS", "log")       # engine pages never retrieved as content (the kb's focus pages are added)


def _layers(cfg: kbconfig.KbConfig | None) -> list[dict]:
    """The `[pages]` tables that apply to `cfg`, most specific first."""
    out: list[dict] = []
    if cfg is None:
        return out
    own = cfg.data.get(TABLE)
    if own is not None:
        out.append(_checked(own, cfg.path))
    if cfg.kit:
        from kb_distillery.config import kit             # lazy, like KbConfig.section
        for name in reversed(kit.chain(cfg.kit)):
            table = kit.load(name).get(TABLE)
            if isinstance(table, dict):
                out.append(table)
    return out


def _checked(table, where: str) -> dict:
    """A kb.toml `[pages]` table, refused with the file named when a value has the wrong shape (the kit's are
    checked the same way in kb_distillery.config.kit.load)."""
    if not isinstance(table, dict):
        raise kbconfig.KbConfigError(f"{where}: [pages] must be a table")
    heading = table.get("takeaways_heading", "x")
    if not (isinstance(heading, str) and heading.strip()):
        raise kbconfig.KbConfigError(f"{where}: [pages] takeaways_heading must be a non-empty string")
    slugs = table.get("focus_slugs", [])
    if not (isinstance(slugs, list) and all(isinstance(s, str) for s in slugs)):
        raise kbconfig.KbConfigError(f"{where}: [pages] focus_slugs must be a list of slugs")
    return table


def setting(key: str, cfg: kbconfig.KbConfig | None = None):
    """`[pages] <key>` for `cfg` (default: the selected kb), else the engine default."""
    if key not in DEFAULTS:
        raise KeyError(f"unknown [pages] key {key!r} (known: {sorted(DEFAULTS)})")
    for table in _layers(cfg if cfg is not None else kbconfig.current()):
        if key in table:
            return table[key]
    return DEFAULTS[key]


def takeaways_heading(cfg: kbconfig.KbConfig | None = None) -> str:
    """The takeaways section title, without `## `: "Takeaways" unless the kit or kb names another."""
    return str(setting("takeaways_heading", cfg))


def focus_slugs(cfg: kbconfig.KbConfig | None = None) -> frozenset[str]:
    """The kb's focus pages (none unless the kit or kb names some)."""
    return frozenset(str(s) for s in setting("focus_slugs", cfg))


def skip_slugs(cfg: kbconfig.KbConfig | None = None) -> frozenset[str]:
    """Pages that are not content for retrieval or orphan checks: the engine's own plus the kb's focus pages."""
    return frozenset(CONVENTION_SLUGS) | focus_slugs(cfg)
