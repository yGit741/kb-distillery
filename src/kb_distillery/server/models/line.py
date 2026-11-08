"""Models of POST /api/line/route: where a plain line of the graph's search line should go."""
from typing import Literal

from pydantic import Field

from kb_distillery.server.models.base import ApiModel


class LineCommand(ApiModel):
    id: str = Field(..., max_length=200)
    label: str = Field(..., max_length=200)


class LineRouteRequest(ApiModel):
    text: str = Field(..., max_length=1000, description="A line the browser's rules could not place")
    commands: list[LineCommand] = Field(default_factory=list, max_length=400,
                                        description="The commands the line offers, by id and name")
    backend: Literal["subscription", "api", "batch"] | None = Field(
        None, description="LLM backend for this request; default $KB_LLM_BACKEND, then subscription. A batch never "
        "answers within the deadline, so it reads as a page search")
    fallback: Literal["subscription", "api", "batch", "none"] | None = Field(
        None, description="Backend tried once when the first one fails. Default none: routing never moves to a paid "
        "backend by itself")


class LineRouteResponse(ApiModel):
    intent: Literal["search", "view", "command", "ask"]
    text: str = Field(..., description="The line to pass on (the model may tidy it)")
    command: str | None = Field(None, description="The command id, only for intent `command`")
    backend: str = Field("", description="The LLM backend that answered; empty when none was asked")
    fallback_from: str | None = None
    usd: float = 0.0
    reason: str = Field("", description="Why the line reads as a search when the model could not place it")
