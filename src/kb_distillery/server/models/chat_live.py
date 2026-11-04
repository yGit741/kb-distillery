"""Chat, agent mode: queue a message into the turn that is running."""
from kb_distillery.server.models.base import ApiModel


class ChatMessageIn(ApiModel):
    """Body of POST /api/chat/message: `text` becomes the next user message of the live turn for `session`."""
    session: str
    text: str


class ChatMessageResult(ApiModel):
    ok: bool = True
