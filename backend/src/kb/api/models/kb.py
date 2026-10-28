from typing import Literal

from kb.api.models.base import ApiModel


class KbGitState(ApiModel):
    repo: bool                      # the folder is its own git repository
    branch: str
    last_tag: str                   # newest kb-x.y.z snapshot tag, "" when none
    dirty: int                      # uncommitted paths (incl. untracked)


class KbType(ApiModel):
    id: str
    label: str
    layer: Literal["source", "collection", "concept"]
    prefix: str
    color: str
    statuses: list[str]


class KbDigestPart(ApiModel):
    part: str                       # focus.md | types.md
    origin: Literal["kb", "explorer"]
    path: str


class KbInfo(ApiModel):
    """The knowledge base this app serves: kb.toml facts, where it is, its types, what it overrides."""
    id: str | None
    name: str
    legacy: bool                    # no kb.toml: the checkout / $KB_ROOT is the vault, types are defaults
    root: str
    config: str | None
    schema_version: str
    git: KbGitState
    think_root: str
    think_git: KbGitState
    types: list[KbType]
    areas: list[str]
    source_fields: list[str]
    digest: list[KbDigestPart]
    flags_registry: Literal["explorer", "kb"]
    meta_overrides: list[str]
    bases_dir: str
    registry: str
    relaunch: str


class KbRow(ApiModel):
    id: str
    root: str
    name: str
    schema_version: str
    error: str
    git: KbGitState
    active: bool


class KbRegister(ApiModel):
    path: str                            # a knowledge base folder: kb.toml at this schema, its own git repository


class KbList(ApiModel):
    bases_dir: str
    registry: str
    registry_exists: bool
    think_root: str
    active: str | None
    kbs: list[KbRow]
