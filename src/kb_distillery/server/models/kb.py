from typing import Literal

from kb_distillery.server.models.base import ApiModel


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
    maturities: list[str]


class KbDigestPart(ApiModel):
    part: str                       # focus.md | types.md
    origin: Literal["kb", "explorer"]
    path: str


class KbInfo(ApiModel):
    """The knowledge base this app serves: kb.toml facts, where it is, its types, what it overrides."""
    id: str | None
    name: str
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
    relaunch: str


class KbRow(ApiModel):
    id: str
    root: str
    name: str
    schema_version: str
    error: str
    git: KbGitState
    active: bool


class KbList(ApiModel):
    bases_dir: str
    think_root: str
    active: str | None
    kbs: list[KbRow]
