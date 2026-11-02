"""kb_distillery.core.frontmatter: the flat shapes stay strings and lists; the OKF shapes parse; every scalar stays a string."""
from kb_distillery.core import frontmatter as fm


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
    assert fm.fill_title("---\ntitle: {{title_yaml}}\n---\n# T: x\n").startswith('---\ntitle: "T: x"')


def test_display_shows_slugs_and_dates():
    assert fm.display("related", ["a.md", "b.md"]) == ["a", "b"]
    assert fm.display("sources", [{"resource": "a.md"}, {"resource": "https://x.org/"}]) == ["a", "https://x.org/"]
    assert fm.display("generated", {"by": "human:ada", "at": "2026-01-01T00:00:00Z"}) == "human:ada @ 2026-01-01T00:00:00Z"
    assert fm.display("created", "2026-10-08T00:00:00Z") == "2026-10-08"
