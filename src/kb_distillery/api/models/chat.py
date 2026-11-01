"""Chat: status, settings, keys (hints only, never key material), prompts, saved chats, the request body."""
from typing import Any, Optional

from kb_distillery.api.models.base import ApiModel


class ChatMessage(ApiModel):
    role: str = ""
    content: str = ""


class ChatRequest(ApiModel):
    """Body of POST /api/chat. Everything but `question` falls back to the stored settings."""
    question: str = ""
    history: list[dict[str, Any]] = []
    model: Optional[str] = None
    backend: Optional[str] = None         # agent | direct
    auth_mode: Optional[str] = None       # api_key | subscription
    active_key: Optional[str] = None
    system: Optional[str] = None
    session: Optional[str] = None
    scope: Optional[str] = None


class KeyEntry(ApiModel):
    name: str
    origin: str
    hint: str = ""                         # "sk-ant-…abcd": the last four characters only


class ChatAuth(ApiModel):
    mode: str = "api_key"
    active_key: str = ""
    keys: list[KeyEntry] = []
    keys_dir: str = ""
    subscription: dict[str, Any] = {}


class ChatStatus(ApiModel):
    key: bool
    key_origin: Optional[str] = None
    key_file: str = ""
    key_hint: str = ""
    key_name: str = ""
    reset_day: int = 30
    backend: str = "agent"
    agent: dict[str, Any] = {}
    auth: ChatAuth
    models: list[dict[str, Any]] = []
    default_model: str = ""
    spend: dict[str, Any] = {}


class ChatSettings(ApiModel):
    key_name: str = ""
    monthly_credit: float = 100.0
    reset_day: int = 30
    backend: str = "agent"
    auth_mode: str = "api_key"
    active_key: str = ""


class ChatSettingsUpdate(ApiModel):
    """Any subset of the settings; validation (ranges, enums) is the service's and answers 400."""
    key_name: Optional[str] = None
    monthly_credit: Optional[float] = None
    reset_day: Optional[int] = None
    backend: Optional[str] = None
    auth_mode: Optional[str] = None
    active_key: Optional[str] = None


class KeyList(ApiModel):
    keys: list[KeyEntry]
    keys_dir: str = ""


class KeyAdd(ApiModel):
    name: str = ""
    key: str = ""


class KeyRemove(ApiModel):
    name: str = ""


class PromptsResponse(ApiModel):
    prompts: list[dict[str, Any]]


class SavedChat(ApiModel):
    title: Optional[str] = None
    messages: list[dict[str, Any]] = []


class SavedChatResult(ApiModel):
    path: str
