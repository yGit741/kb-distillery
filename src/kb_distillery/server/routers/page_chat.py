"""Chat on a page: /api/pages/{slug}/chat turns the owner's message into a proposal (never a direct write), plus the
page's thread and the @mention picker. Thin over `kb_distillery.proposals.chat`."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from kb_distillery.proposals import chat as svc
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.models.page_chat import MentionList, PageChatReply, PageChatRequest, PageChatThread
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["pages"])
ERRORS = {400: {}, 404: {}, 405: {}, 422: {}, 502: {}}


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ProposalError as e:
        return JSONResponse({"detail": str(e), **e.extra}, status_code=e.status)


@router.get("/api/pages/mentions", response_model=MentionList, summary="Pages for the @mention picker (prefix, then fuzzy)")
def mentions(q: str = Query("", description="what the owner typed after @")):
    return _call(lambda: {"pages": svc.mentions(q)})


@router.get("/api/pages/{slug}/chat", response_model=PageChatThread, responses=ERRORS,
            summary="The page's chat thread: messages and the proposals they produced")
def get_thread(slug: str):
    return _call(svc.thread, slug)


@router.post("/api/pages/{slug}/chat", dependencies=[Depends(refuse_when_read_only)], response_model=PageChatReply,
             responses=ERRORS, summary="Ask about the page; edits come back as a proposal to review")
def post_chat(slug: str, body: PageChatRequest):
    return _call(svc.chat, slug, body.message, [s.model_dump() for s in body.selections], body.mentions,
                 backend=body.backend)
