"""Closed-world PDF verifier (dark behind the `parsed-pdf` flag): the PDF's own text layer is the truth, a parser's
Markdown is checked against it page by page — nothing lost, nothing invented, accents where the glyphs put them.

layer -> reconcile -> structure; mutate measures the verifier; store keeps verified pages under meta/parsed/<raw-sha1>/.
Not wired into ingest yet (a later PR hooks `extract_text`)."""

FLAG = "parsed-pdf"


def enabled() -> bool:
    """Effective value of the `parsed-pdf` flag (a test's forced state wins; otherwise the registry's local value)."""
    from kb_distillery.flags import registry
    forced = registry.forced(FLAG)
    if forced is not None:
        return forced
    return registry.value(FLAG, "local")
