"""POST /api/chat/message: a message sent while the agent runs is queued into the live turn (agent-mode flag)."""
from fastapi import APIRouter
from starlette.responses import JSONResponse

from kb_distillery.config.flags import runtime
from kb_distillery.server.models.chat_live import ChatMessageIn, ChatMessageResult
from kb_distillery.services import chat_live

router = APIRouter(tags=["chat"])


@router.post("/api/chat/message", response_model=ChatMessageResult, summary="Queue a message into the running agent turn",
             responses={404: {"description": "no turn is running for that session"}})
def post_message(body: ChatMessageIn):
    text = body.text.strip()
    if not runtime.effective("agent-mode") or not text or not chat_live.send(body.session, text):
        return JSONResponse({"error": "no turn is running", "hint": "stop and resume the session with a normal message"},
                            status_code=404)
    return {"ok": True}
