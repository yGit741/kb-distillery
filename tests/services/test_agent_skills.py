"""Agent-mode skills: the whitelist, the generated plugin, the subagent and the policy for Skill / Agent / Task.
No network and no real LLM; the kb config is faked."""
import json
import os
from types import SimpleNamespace

import pytest

from kb_distillery.config import kb as kbconfig
from kb_distillery.services import agent_skills, chat_agent


@pytest.fixture(autouse=True)
def no_kb(monkeypatch):
    monkeypatch.setenv("KB_APP_CONFIG", "/nonexistent/app.toml")
    monkeypatch.setattr(kbconfig, "current", lambda: None)          # no kb: the base kit's defaults


def with_kb(monkeypatch, agent_table, kit="base"):
    data = {"agent": agent_table} if agent_table is not None else {}
    monkeypatch.setattr(kbconfig, "current", lambda: SimpleNamespace(kit=kit, data=data))


def allowed(tool, inp):
    return chat_agent.tool_policy(tool, inp).allow


def test_kit_default_whitelists_deep_research():
    assert agent_skills.configured() == ["deep-research"]
    assert agent_skills.enabled() == ["deep-research"]


def test_kb_toml_replaces_the_kit_default(monkeypatch):
    with_kb(monkeypatch, {"skills": []})
    assert agent_skills.enabled() == []
    with_kb(monkeypatch, {"skills": ["deep-research", "deep-research"]})
    assert agent_skills.enabled() == ["deep-research"]
    with_kb(monkeypatch, {})
    assert agent_skills.enabled() == ["deep-research"]              # no key: the kit default


@pytest.mark.parametrize("name", ["wiki-edit", "create-skill", "no-such-skill", "../x", "kbd:deep-research"])
def test_listed_but_write_dev_or_unknown_skills_never_enable(monkeypatch, name):
    with_kb(monkeypatch, {"skills": [name]})
    assert agent_skills.enabled() == []


@pytest.mark.flag("agent-mode", True)
def test_only_whitelisted_skills_are_allowed():
    assert allowed("Skill", {"skill": "deep-research"})
    assert allowed("Skill", {"skill": "kbd:deep-research"})
    for other in ("wiki-edit", "design", "kbd:wiki-edit", "other:deep-research", "", None):
        assert not allowed("Skill", {"skill": other}), other
    assert not allowed("Skill", {})


@pytest.mark.flag("agent-mode", True)
def test_empty_whitelist_denies_every_skill_and_subagent(monkeypatch):
    with_kb(monkeypatch, {"skills": []})
    assert not allowed("Skill", {"skill": "deep-research"})
    assert not allowed("Agent", {"subagent_type": agent_skills.SUBAGENT})
    assert agent_skills.subagents() == {}


@pytest.mark.flag("agent-mode", True)
def test_only_the_defined_subagent_may_start():
    assert allowed("Agent", {"subagent_type": "kb-researcher", "prompt": "x"})
    assert allowed("Task", {"subagent_type": "kb-researcher", "prompt": "x"})
    for other in ("general-purpose", "Explore", "Plan", "", None):
        assert not allowed("Agent", {"subagent_type": other}), other
    assert not allowed("Task", {"prompt": "x"})


def test_subagent_tools_are_the_read_only_set():
    spec = agent_skills.subagents()["kb-researcher"]
    assert set(spec["tools"]) <= set(chat_agent.TOOLS) | set(chat_agent.WEB_TOOLS)
    assert not set(spec["tools"]) & {"Write", "Edit", "MultiEdit", "NotebookEdit", "Skill", "Agent", "Task", "TodoWrite"}
    assert {"description", "prompt", "tools"} <= set(spec)


@pytest.mark.flag("agent-mode", True)
def test_subagent_calls_hit_the_same_policy():
    """A subagent's tool calls reach the same hook: writes and arbitrary shell stay denied with the flag on."""
    assert not allowed("Write", {"file_path": "wiki/x.md", "content": "y"})
    assert not allowed("Bash", {"command": "rm -rf wiki"})
    assert not allowed("Edit", {"file_path": "wiki/x.md"})


@pytest.mark.flag("agent-mode", False)
def test_flag_off_denies_skills_and_subagents():
    assert not allowed("Skill", {"skill": "deep-research"})
    assert not allowed("Agent", {"subagent_type": "kb-researcher"})
    assert not allowed("Task", {"subagent_type": "kb-researcher"})


@pytest.mark.flag("agent-mode", False)
def test_flag_off_request_is_unchanged():
    req = chat_agent.agent_request("q", "sonnet", "SYS")
    assert req.tools == tuple(chat_agent.TOOLS) and req.disallowed == tuple(chat_agent.DISALLOWED_TOOLS)
    assert not req.skills and not req.plugins and not req.agents


@pytest.mark.flag("agent-mode", True)
def test_flag_on_request_carries_skills_plugin_and_subagent(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_skills, "CACHE_PATH", str(tmp_path))
    req = chat_agent.agent_request("q", "sonnet", "SYS")
    assert req.skills == ("kbd:deep-research",)
    assert set(req.agents) == {"kb-researcher"}
    assert "Skill" in req.tools and "Agent" in req.tools
    assert not {"Skill", "Agent", "Task"} & set(req.disallowed)
    assert {"Write", "Edit"} <= set(req.disallowed)
    (plugin,) = req.plugins
    assert plugin.startswith(str(tmp_path))
    assert json.load(open(os.path.join(plugin, ".claude-plugin", "plugin.json")))["name"] == "kbd"
    assert open(os.path.join(plugin, "skills", "deep-research", "SKILL.md"), encoding="utf-8").read().startswith("---")


@pytest.mark.flag("agent-mode", True)
def test_flag_on_with_empty_whitelist_adds_nothing(monkeypatch):
    with_kb(monkeypatch, {"skills": []})
    req = chat_agent.agent_request("q", "sonnet", "SYS")
    assert req.tools == tuple(chat_agent.TOOLS) and not req.skills and not req.plugins and not req.agents


def test_plugin_dir_is_content_addressed_and_idempotent(tmp_path):
    a = agent_skills.plugin_dir(["deep-research"], base=str(tmp_path))
    marker = os.path.join(a, "marker")
    open(marker, "w").close()
    assert agent_skills.plugin_dir(["deep-research"], base=str(tmp_path)) == a
    assert os.path.exists(marker)                                   # reused, not rebuilt
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
