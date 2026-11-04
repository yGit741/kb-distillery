"""Per-session skill toggles for the chat agent (agent-mode flag).

The list is the kb's whitelist (`[agent] skills` of kb.toml, else the kit's); a session may turn some of them off, which is
stored beside the session under `<kb>/.local/sessions/` (never committed, never `wiki/`). The kb.toml is never written and
nothing outside the whitelist can be switched on. Errors keep the chat shape {"error": …}.
"""
from fastapi import APIRouter
from starlette.responses import JSONResponse

from kb_distillery.config.flags import runtime
from kb_distillery.server.models.chat_skills import ChatSkillList, ChatSkillsPut
from kb_distillery.services import agent_skills, sessions_store

router = APIRouter(tags=["chat"])


def _err(code, message):
    return JSONResponse({"error": message}, status_code=code)


def _off():
    return None if runtime.effective("agent-mode") else _err(404, "agent mode is off")


def _listing(session):
    on = set(agent_skills.session_selection(session)) if session else None
    return {"skills": [{**s, "enabled": on is None or s["name"] in on} for s in agent_skills.catalog()], "session": session}


@router.get("/api/chat/skills", response_model=ChatSkillList, summary="Whitelisted skills and which are on for a session",
            responses={400: {}, 404: {}})
def get_skills(session: str | None = None):
    if (off := _off()):
        return off
    try:
        return _listing(sessions_store.clean_id(session) if session else None)
    except sessions_store.SessionsError as exc:
        return _err(exc.status, str(exc))


@router.put("/api/chat/skills/{session_id}", response_model=ChatSkillList, summary="Choose the skills on for a session",
            responses={400: {}, 404: {}, 405: {}})
def put_skills(session_id: str, body: ChatSkillsPut):
    if (off := _off()):
        return off
    try:
        sid = sessions_store.clean_id(session_id)
        agent_skills.save_session_selection(sid, body.enabled)
        return _listing(sid)
    except sessions_store.SessionsError as exc:
        return _err(exc.status, str(exc))
