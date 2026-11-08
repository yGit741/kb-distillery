"""Where a plain line of the graph's search line should go: page search, a view change, a command, or a question.

The browser reads the line with rules first (`web/src/features/graph/shell/lineRoute.ts`, no model): an exact page
title, view words, a question, a command name. Only a line those rules cannot place comes here. One tiny prompt (the
four intents and the command names the browser offers) goes through the shared LLM tool (`kb_distillery.llm`), with a
short deadline. Any failure (no backend, a slow or broken answer, an unknown command) reads the line as a page search,
so the caller never sees an error from here.

Backends: `subscription` by default (`$KB_LLM_BACKEND`); `api` and `batch` are selectable per request. There is no
silent fallback to a paid backend unless the caller names one; a batch never answers within the deadline, so it lands
as a page search.
"""
import concurrent.futures

from kb_distillery import llm

MODEL = "light"
EFFORT = "low"
MAX_TOKENS = 200
TIMEOUT_S = 15.0
INTENTS = ("search", "view", "command", "ask")
COMMANDS_SHOWN = 120


def build_prompt(text, commands):
    names = "\n".join(f"- {c['id']}: {c['label']}" for c in commands[:COMMANDS_SHOWN]) or "- none"
    return f"""Classify one line typed into a knowledge-base graph's search box. Intents:
- search: find a page by its name or words
- view: change what the graph shows (filter, hide, show only, colour, size, group, layout)
- command: run one of the commands below
- ask: a question for the chat agent
Commands (id: name):
{names}
Reply with one JSON object and nothing else: {{"intent": "search|view|command|ask", "text": "<the line to pass on, cleaned>", "command": "<command id, only for command>"}}

Line: {text}
"""


def _search(text, why, backend=""):
    return {"intent": "search", "text": text, "command": None, "backend": backend, "fallback_from": None, "usd": 0.0,
            "reason": why}


def parse_answer(reply, text, commands):
    """The model's reply → (intent, text, command id); ValueError when it is not one of the four or names no command."""
    data = llm.json_object(reply)
    if data is None:
        raise ValueError("the reply was not a JSON object")
    intent = str(data.get("intent") or "").strip().lower()
    if intent not in INTENTS:
        raise ValueError(f"unknown intent {intent!r}")
    said = data.get("text")
    out = said.strip() if isinstance(said, str) and said.strip() else text
    if intent != "command":
        return intent, out, None
    cid = str(data.get("command") or "").strip()
    if cid not in {c["id"] for c in commands}:
        raise ValueError(f"no command {cid!r}")
    return intent, out, cid


def _ask(prompt, backend, fallback, timeout_s):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(llm.ask, prompt, backend=backend, fallback=fallback, model=MODEL, effort=EFFORT,
                          max_tokens=MAX_TOKENS, id="line-route",
                          run_kw={"wait_s": timeout_s, "poll_every": 2} if backend == "batch" else None)
        return fut.result(timeout=timeout_s)
    finally:
        pool.shutdown(wait=False)       # a late answer is dropped; the line has moved on


def route(text, commands=(), *, backend=None, fallback=None, timeout_s=TIMEOUT_S):
    """A line → {intent, text, command, backend, fallback_from, usd, reason}. `commands` are {id, label} dicts. Never
    raises for the model's sake: a failure reads the line as a page search and says why in `reason`."""
    text = (text or "").strip()
    commands = [{"id": str(c["id"]), "label": str(c["label"])} for c in commands]
    if not text:
        return _search(text, "empty line")
    try:
        b = llm.resolve_backend(backend)
        fb = None if fallback in (None, "none") else llm.resolve_backend(fallback)
    except llm.LLMError as e:
        return _search(text, str(e))
    try:
        res = _ask(build_prompt(text, commands), b, fb, timeout_s)
    except concurrent.futures.TimeoutError:
        return _search(text, f"the {b} backend did not answer within {timeout_s:g}s", b)
    except Exception as e:  # noqa: BLE001 - any failure of the model reads the line as a search
        return _search(text, f"the {b} backend failed: {e}", b)
    used = getattr(res, "backend_used", "") or res.backend or b
    if res.error and not res.text:
        return _search(text, f"the {used} backend failed: {res.error}", used)
    try:
        intent, out, cid = parse_answer(res.text, text, commands)
    except ValueError as e:
        return _search(text, f"the answer was not usable: {e}", used)
    return {"intent": intent, "text": out, "command": cid, "backend": used,
            "fallback_from": getattr(res, "fallback_from", "") or None, "usd": round(res.usd or 0.0, 6), "reason": ""}
