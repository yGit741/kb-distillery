"""The research kit's AGENTS template carries the research-specific text; the engine's own AGENTS.md carries none of it."""
import os
import re

from kb_distillery import init_kb

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def render(kit):
    return init_kb.render_template(kit, init_kb.AGENTS_FILE, {"name": "Notes", "kb_id": "notes", "kit": kit})


def test_research_template_adds_its_rows_on_top_of_the_base_text():
    base, research = render("base"), render("research")
    assert "## Hard rules" in research and "## Doc router" in research  # {{parent}} brings the whole base text
    assert research.index("## Doc router") < research.index("## Research kit additions")
    assert "### Intent router additions" in research and "build-researcher-profile" in research
    assert "Intent router additions" not in base and "build-researcher-profile" not in base
    assert not re.search(r"\{\{|\}\}", research)


def test_engine_agents_md_is_about_the_engine_not_a_kb():
    text = open(os.path.join(REPO, "AGENTS.md"), encoding="utf-8").read()
    assert text.startswith("# kb-distillery")
    assert not re.search(r"MSc|Karpathy|build-researcher-profile|propose-relations", text)
    for skill in sorted(os.listdir(os.path.join(REPO, ".claude", "skills"))):
        if os.path.isfile(os.path.join(REPO, ".claude", "skills", skill, "SKILL.md")) and skill != "share-kb":
            assert f"`{skill}`" in text, f"the intent router does not name the dev skill {skill}"
