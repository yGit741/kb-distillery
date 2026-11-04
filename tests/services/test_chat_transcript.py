"""Chat transcript (agent mode): thinking, tool results, the todo list and mid-turn messages. No SDK, no network."""
import asyncio
import threading

import pytest

from kb_distillery.services import chat_agent, chat_live


def cls(cls_name, **fields):
    return type(cls_name, (), {"__init__": lambda self, **kw: self.__dict__.update({**fields, **kw})})


StreamEvent = cls("StreamEvent", event=None, parent_tool_use_id=None)
AssistantMessage = cls("AssistantMessage", content=None)
UserMessage = cls("UserMessage", content=None)
ToolUseBlock = cls("ToolUseBlock", id=None, name="", input=None)
ToolResultBlock = cls("ToolResultBlock", tool_use_id=None, is_error=False, content=None)


def think(text):
    return StreamEvent(event={"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": text}})


def run(msgs):
    state = chat_agent.TurnState(index={})
    out = []
    for m in msgs:
        out += chat_agent.map_message(m, state)
    return out


@pytest.mark.flag("agent-mode", True)
def test_thinking_deltas_stream_as_thinking_events():
    assert run([think("hm"), think("")]) == [("thinking", "hm")]


@pytest.mark.flag("agent-mode", False)
def test_thinking_is_dropped_with_the_flag_off():
    assert run([think("hm")]) == []


@pytest.mark.flag("agent-mode", True)
def test_tool_lines_carry_status_and_a_result_preview():
    use = AssistantMessage(content=[ToolUseBlock(id="t1", name="Grep", input={"pattern": "rank"})])
    res = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content=[{"type": "text", "text": "x" * 400}])])
    ev = run([use, res])
    assert ev[0][1]["status"] == "running"
    done = ev[1][1]
    assert done["status"] == "done" and done["id"] == "t1" and len(done["result"]) == 301 and done["result"].endswith("…")


@pytest.mark.flag("agent-mode", True)
def test_a_failed_tool_result_is_an_error_line():
    use = AssistantMessage(content=[ToolUseBlock(id="t1", name="Read", input={"file_path": "/nope"})])
    res = UserMessage(content=[ToolResultBlock(tool_use_id="t1", is_error=True, content="denied")])
    last = run([use, res])[-1][1]
    assert (last["status"], last["error"], last["result"]) == ("error", True, "denied")


@pytest.mark.flag("agent-mode", False)
def test_tool_events_are_unchanged_with_the_flag_off():
    use = AssistantMessage(content=[ToolUseBlock(id="t1", name="Grep", input={"pattern": "rank"})])
    ok = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="hits")])
    ev = run([use, ok])
    assert ev == [("tool", {"name": "Grep", "summary": "grep rank", "id": "t1"})]


@pytest.mark.flag("agent-mode", True)
def test_todowrite_becomes_a_todo_event_not_a_tool_line():
    todos = [{"content": "Read pages", "status": "completed", "activeForm": "Reading"},
             {"content": "Answer", "status": "in_progress", "activeForm": "Answering"}]
    ev = run([AssistantMessage(content=[ToolUseBlock(id="t2", name="TodoWrite", input={"todos": todos})])])
    assert ev == [("todo", {"items": [{"content": "Read pages", "status": "completed"},
                                      {"content": "Answer", "status": "in_progress"}]})]


@pytest.mark.flag("agent-mode", True)
def test_agent_mode_requests_thinking_and_allows_todowrite():
    req = chat_agent.agent_request("q", "sonnet", "sys", effort="high")
    assert req.thinking and "TodoWrite" in req.tools and "TodoWrite" not in req.disallowed
    assert chat_agent.tool_policy("TodoWrite", {"todos": []}).allow


@pytest.mark.flag("agent-mode", False)
def test_flag_off_requests_no_thinking_and_denies_todowrite():
    req = chat_agent.agent_request("q", "sonnet", "sys")
    assert not req.thinking and "TodoWrite" not in req.tools and "TodoWrite" in req.disallowed
    assert not chat_agent.tool_policy("TodoWrite", {"todos": []}).allow


# ── mid-turn messages ──

class FakeClient:
    """Records queries; `query` and `interrupt` are coroutines like the SDK's."""
    def __init__(self):
        self.sent, self.interrupted = [], 0

    async def query(self, text):
        self.sent.append(text)

    async def interrupt(self):
        self.interrupted += 1


def on_loop():
    """A running event loop in a thread, the way the agent turn runs."""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, lambda: (loop.call_soon_threadsafe(loop.stop), t.join(2))


def test_send_queues_into_the_live_client_and_echoes():
    events, loop_stop = [], None
    loop, loop_stop = on_loop()
    live = chat_live.Live(events.append)
    client = FakeClient()
    live.attach(client, loop)
    chat_live.register("s1", live)
    try:
        assert chat_live.send("s1", "also check X")
        assert client.sent == ["also check X"] and events == [("user", {"text": "also check X"})]
        assert live.take_pending() is True and live.take_pending() is False     # one queued turn, then closed
        assert not chat_live.send("s1", "too late")                              # the handle is closed
        live.interrupt()
        assert client.interrupted == 0                                          # closed: nothing to interrupt
    finally:
        chat_live.unregister(live)
        loop_stop()
    assert not chat_live.send("s1", "gone")


def test_send_is_refused_before_the_client_is_attached():
    live = chat_live.Live(lambda e: None)
    chat_live.register("s2", live)
    try:
        assert not chat_live.send("s2", "hi")
        assert not chat_live.send("unknown", "hi")
    finally:
        chat_live.unregister(live)


def test_interrupt_reaches_the_client():
    loop, stop = on_loop()
    live = chat_live.Live(lambda e: None)
    client = FakeClient()
    live.attach(client, loop)
    try:
        live.interrupt()
        for _ in range(100):
            if client.interrupted:
                break
            asyncio.run(asyncio.sleep(0.01))
        assert client.interrupted == 1
    finally:
        stop()
