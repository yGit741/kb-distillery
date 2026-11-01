"""GET /api/flags, PUT /api/flags/{name} — mirrors kb_distillery.services.flags.list_flags()."""
from typing import Literal

from pydantic import BaseModel

from kb_distillery.api.models.base import ApiModel


class FlagEnvs(ApiModel):
    local: bool
    private: bool
    public: bool


class FlagState(ApiModel):
    name: str
    description: str
    owner: str
    created: str
    expires: str
    kind: Literal["runtime", "build"]
    default: bool
    envs: FlagEnvs
    registry_value: bool                          # meta/flags.toml value for this env
    value: bool                                   # effective value (override wins, runtime flags only)
    source: Literal["registry", "override"]
    overridden_at: str | None = None


class FlagsSnapshot(ApiModel):
    env: Literal["local", "private", "public"]
    registry: Literal["explorer", "kb"] = "explorer"   # explorer meta-defaults/flags.toml or the kb's own meta/flags.toml
    flags: list[FlagState]
    overrides: dict[str, bool]                    # name -> value, only flags with an override


class FlagOverride(BaseModel):
    value: bool | None                            # null clears the override
