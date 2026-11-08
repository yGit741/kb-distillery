"""Chat: POST /api/chat streams server-sent events; status, settings, keys, prompts, saved chats around it.

Errors keep the legacy shape: 400/500 with {"error": …, "hint"?: …}. Key material never leaves the process:
every response carries hints (`sk-ant-…abcd`) only.
"""
from fastapi import APIRouter
from starlette.responses import JSONResponse

from kb_distillery.config.flags import runtime
from kb_distillery.server.models.chat import (ChatAnswer, ChatAnswerResult, ChatRequest, ChatSettings, ChatSettingsUpdate, ChatStatus, KeyAdd, KeyList,
                                KeyRemove, PromptsResponse, SavedChat, SavedChatResult)
from kb_distillery.server.readonly import is_read_only
from kb_distillery.server.sse import sse_response
from kb_distillery.services import agent_skills, sessions_store
from kb_distillery.services import chat as chat_data
from kb_distillery.services import chat_agent
from kb_distillery.services import chat_attachments

router = APIRouter(tags=["chat"])


def _err(code, message, hint=None):
    body = {"error": message}
    if hint:
        body["hint"] = hint
    return JSONResponse(body, status_code=code)


def direct_events(payload, key, model, question, history, scope):
    """The direct backend as (event, data) pairs: sources, delta*, usage, done (or error)."""
    hits, new_slugs = chat_data.plan_turn(history, question, scope=scope)
    system = chat_data.build_system(payload.get("system") or "", scope=scope)
    messages = chat_data.build_messages(history, question, new_slugs)
    yield "sources", {"hits": hits, "new": new_slugs}
    try:
        for kind, value in chat_data.stream_claude(system, messages, model, key):
            if kind == "text":
                yield "delta", value
                continue
            cost = chat_data.record_usage(model, value)
            yield "usage", {**value, "model": model, "cost_usd": cost, "spend": chat_data.spend_summary()}
        yield "done", {}
    except chat_data.ChatError as exc:
        yield "error", {"error": str(exc)}


@router.post("/api/chat", summary="Ask the research chat (server-sent events)",
             responses={200: {"content": {"text/event-stream": {}}}, 400: {"description": "bad request"}})
def post_chat(req: ChatRequest):
    if is_read_only():
        return _err(405, "this server is read-only (KB_READ_ONLY is set): the chat is not available here")
    payload = req.model_dump(exclude_none=True)
    settings = chat_data.load_settings()
    auth_mode = payload.get("auth_mode") or settings["auth_mode"]
    if auth_mode not in chat_data.AUTH_MODES:
        return _err(400, f"unknown auth_mode {auth_mode!r}")
    backend = payload.get("backend") or settings["backend"]
    if backend not in chat_data.BACKENDS:
        return _err(400, f"unknown backend {backend!r}")
    billing = payload.get("billing") if runtime.effective("agent-mode") and backend == "agent" else None
    if billing:       # the composer line's pick decides who pays; it replaces the stored account choice for this turn
        auth_mode = "subscription" if billing == "subscription" else "api_key"
    if auth_mode == "subscription":
        if backend != "agent":
            return _err(400, "the subscription works with the Agent backend only",
                        "switch Backend to Agent, or pick an API key")
        sub = chat_agent.subscription_status()
        if not sub["logged_in"]:
            return _err(400, "Claude subscription not available", sub["error"] or "run `claude login` in a terminal")
        key = None
    else:
        if payload.get("active_key"):
            settings = {**settings, "active_key": payload["active_key"]}
        key, _ = chat_data.load_api_key(settings)
        if not key:
            return _err(400, "no API key", "add one in the Session card, create "
                        f"{chat_data.KEY_FILE} (read on every message) or start with ANTHROPIC_API_KEY set")
    question = (payload.get("question") or "").strip()
    if not question:
        return _err(400, "empty question")
    model = payload.get("model") if payload.get("model") in chat_data.MODEL_IDS else chat_data.DEFAULT_MODEL
    history = [m for m in (payload.get("history") or []) if isinstance(m, dict)]
    scope = None
    scope_slug = (payload.get("scope") or "").strip()
    if scope_slug:
        from kb_distillery.vault import scopes as scope_lib
        try:
            scope = scope_lib.scope_context(scope_slug, chat_data.ROOT)
        except scope_lib.ScopeUnknown as exc:
            return _err(400, str(exc))
    if backend == "agent":
        info = chat_agent.sdk_info()
        if not info["available"]:
            return _err(400, "agent backend unavailable", f"{info['error']}; or switch the backend to Direct")
        system = chat_agent.build_agent_system(payload.get("system") or "", scope=scope)
        extra = {}
        if runtime.effective("agent-mode"):       # ship dark: the new fields are ignored until the flag is on
            extra = {"effort": payload.get("effort"), "budget": payload.get("budget")}
            if payload.get("skills") is not None:
                extra["skills"] = payload["skills"]      # narrowed to the whitelist inside agent_skills
            elif payload.get("skills_session"):          # the subset saved with the session (the panel may not have loaded)
                try:
                    extra["skills"] = agent_skills.session_selection(payload["skills_session"])
                except sessions_store.SessionsError:     # an id of another shape (an old local chat): the whole whitelist
                    pass
            if payload.get("attachment_session"):
                try:
                    chat_attachments.session_dir(payload["attachment_session"])
                    extra["attachment_session"] = payload["attachment_session"]
                except chat_attachments.AttachmentError as exc:
                    return _err(400, exc.message)
            if payload.get("attachments"):
                try:
                    extra["attachments"] = chat_attachments.resolve(payload.get("attachment_session"),
                                                                    payload["attachments"])
                except chat_attachments.AttachmentError as exc:
                    return _err(400, exc.message)
        gen = chat_agent.stream_agent(question, model=model, system=system, key=key,
                                      billing=billing or ("subscription" if key is None else "api"),
                                      session_id=payload.get("session") or None, history=history, scope=scope,
                                      **extra)
    else:
        gen = direct_events(payload, key, model, question, history, scope)
    return sse_response(gen)


@router.post("/api/chat/answer", response_model=ChatAnswerResult, summary="Answer the agent's question (an `ask` event)",
             responses={404: {"description": "no question is waiting under that id"}})
def post_answer(body: ChatAnswer):
    if is_read_only():
        return _err(405, "this server is read-only (KB_READ_ONLY is set): the chat is not available here")
    if not chat_agent.ASKS.answer(body.session, body.id, body.answers):
        return _err(404, "no question is waiting", "it timed out, was answered already, or the chat was closed")
    return {"ok": True}


@router.get("/api/chat/status", response_model=ChatStatus, summary="Backend, auth, keys (hints) and spend")
def get_status():
    return chat_data.status()


@router.get("/api/chat/prompts", response_model=PromptsResponse, summary="Prompt presets")
def get_prompts():
    return {"prompts": chat_data.list_prompts()}


@router.get("/api/chat/settings", response_model=ChatSettings, summary="Stored chat settings")
def get_settings():
    return chat_data.load_settings()


@router.post("/api/chat/settings", response_model=ChatStatus, summary="Update chat settings",
             responses={400: {"description": "invalid setting"}})
def post_settings(body: ChatSettingsUpdate):
    try:
        chat_data.save_settings(body.model_dump(exclude_none=True))
    except (ValueError, TypeError) as exc:
        return _err(400, str(exc))
    except OSError as exc:
        return _err(500, f"cannot write settings: {exc}")
    return chat_data.status()


@router.get("/api/chat/keys", response_model=KeyList, summary="Stored keys (hints only)")
def get_keys():
    return {"keys": chat_data.list_keys(), "keys_dir": chat_data.KEYS_DIR}


@router.post("/api/chat/keys", response_model=ChatStatus, summary="Store a key and make it active",
             responses={400: {"description": "invalid key"}})
def post_key(body: KeyAdd):
    try:
        entry = chat_data.add_key(body.name, body.key)
        chat_data.save_settings({"active_key": entry["name"], "auth_mode": "api_key"})
    except (ValueError, TypeError) as exc:
        return _err(400, str(exc))
    except OSError as exc:
        return _err(500, f"cannot write key: {exc}")
    return chat_data.status()


def _remove_key(name):
    try:
        chat_data.remove_key(name)
        if chat_data.load_settings().get("active_key") == name:
            chat_data.save_settings({"active_key": ""})
    except (ValueError, TypeError) as exc:
        return _err(400, str(exc))
    except OSError as exc:
        return _err(500, f"cannot write key: {exc}")
    return chat_data.status()


@router.delete("/api/chat/keys/{name}", response_model=ChatStatus, summary="Remove a stored key",
               responses={400: {"description": "unknown key"}})
def delete_key(name: str):
    return _remove_key(name)


@router.post("/api/chat/keys/remove", response_model=ChatStatus, summary="Remove a stored key (legacy shape)",
             responses={400: {"description": "unknown key"}})
def post_key_remove(body: KeyRemove):
    return _remove_key(body.name)


@router.post("/api/chat/saved", response_model=SavedChatResult, summary="Save a chat to raw/inbox/",
             responses={400: {"description": "nothing to save"}})
def post_saved(body: SavedChat):
    try:
        rel = chat_data.save_chat(body.model_dump(exclude_none=True), inbox=chat_data.INBOX)
    except ValueError as exc:
        return _err(400, str(exc))
    return {"path": rel}
