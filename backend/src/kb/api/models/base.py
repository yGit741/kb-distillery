from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base of every API model.

    `extra="allow"` keeps the JSON a typed route returns identical to what the legacy endpoint of the same
    name returned (the old pages read fields the models do not list yet). Tighten a model to
    `extra="forbid"`/`"ignore"` only when its legacy page is deleted.
    """
    model_config = ConfigDict(extra="allow")
