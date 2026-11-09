from kb_distillery.vault import links


def test_targets_returns_fresh_list_each_call():
    text = "see [A](a.md) and [[b]] <!-- [C](c.md) -->"
    first = links.targets(text)
    assert first == ["a", "b"]
    first.append("zzz")
    assert links.targets(text) == ["a", "b"]


def test_targets_handles_empty():
    assert links.targets("") == []
    assert links.targets(None) == []
