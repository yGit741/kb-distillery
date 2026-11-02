"""kb_distillery.vault.frontmatter: the flat shapes stay strings and lists; the OKF shapes parse; every scalar stays a string."""
from kb_distillery.vault import frontmatter as fm


def parse(*lines):
    return fm.parse("---\n" + "\n".join(lines) + "\n---\n\nbody\n")[0]


def test_flat_values_are_strings_and_lists():
    p = parse("type: paper", "area: [a, b]", "created: 2026-10-08T00:00:00Z", "title: \"A # B\"  # note", "url: https://x.org/#frag")
    assert p == {"type": "paper", "area": ["a", "b"], "created": "2026-10-08T00:00:00Z", "title": '"A # B"',
                 "url": "https://x.org/#frag"}


def test_generated_and_sources_flow_forms():
    p = parse("generated: {by: human:ada, at: 2026-10-31T09:46:51+02:00}",
              'sources: [{resource: a.md}, {resource: "https://x.org/?id=1"}, {resource: "think:My Note.md"}]')
    assert p["generated"] == {"by": "human:ada", "at": "2026-10-31T09:46:51+02:00"}
    assert fm.resources(p) == ["a.md", "https://x.org/?id=1", "think:My Note.md"]


def test_block_lists_only_for_the_okf_keys():
    p = parse("related:", "  - a.md", "  - b.md", "relations:", "  - to: x", "    kind: uses", "type: idea")
    assert p["related"] == ["a.md", "b.md"] and p["relations"] == "" and p["type"] == "idea"


def test_quote_scalar_title_helpers():
    assert fm.quote('a "b" \\ c') == '"a \\"b\\" \\\\ c"'
    assert fm.unquote(fm.quote('a "b" \\ c')) == 'a "b" \\ c'
    assert fm.scalar("a.md") == "a.md" and fm.scalar("https://x.org/?id=1").startswith('"')
    assert fm.first_heading("---\ntype: x\n---\n\n# See [[a|Label]] now\n") == "See Label now"
    assert fm.first_heading("```\n# no\n```\n# yes\n") == "yes"
    assert fm.fill_title("---\ntitle: {{title_yaml}}\n---\n# T: x\n") == "---\n---\n# T: x\n"      # the title is the H1: no line


def test_title_is_written_only_when_it_differs_from_the_heading():
    assert fm.title_line("Same  Title") == "" and fm.title_line("Same Title", "Same Title") == ""
    assert fm.title_line("Distilled · Label", "Distilled · [[a|Label]]") == ""
    assert fm.title_line("Other", "Same Title") == 'title: "Other"'
    page = "---\ntype: x\n---\n\n# Heading\n"
    assert fm.page_title({}, page, "slug") == "Heading" and fm.page_title({"title": '"Own"'}, page, "slug") == "Own"
    assert fm.page_title({}, "---\ntype: x\n---\nno heading\n", "slug") == "slug"


def test_a_source_page_url_stands_in_for_the_sources_it_leaves_out():
    src = {"layer": "source", "url": "https://x.org/a"}
    assert fm.resources(src) == ["https://x.org/a"]
    assert fm.resources({**src, "sources": [{"resource": "a.md"}]}) == ["a.md"]       # present sources win
    assert fm.resources({"layer": "concept", "url": "https://x.org/a"}) == []
    assert fm.resources({"layer": "source", "url": "raw/x.pdf"}) == []
    shown = fm.effective({**src, "type": "paper"}, "---\ntype: paper\n---\n# H\n")
    assert shown["title"] == '"H"' and shown["sources"] == [{"resource": "https://x.org/a"}]
    assert fm.display("sources", shown["sources"]) == ["https://x.org/a"]


def test_display_shows_slugs_and_dates():
    assert fm.display("related", ["a.md", "b.md"]) == ["a", "b"]
    assert fm.display("sources", [{"resource": "a.md"}, {"resource": "https://x.org/"}]) == ["a", "https://x.org/"]
    assert fm.display("generated", {"by": "human:ada", "at": "2026-01-01T00:00:00Z"}) == "human:ada @ 2026-01-01T00:00:00Z"
    assert fm.display("created", "2026-10-08T00:00:00Z") == "2026-10-08"
