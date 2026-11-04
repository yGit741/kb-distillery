from pydantic import Field

from kb_distillery.server.models.base import ApiModel


class ChatSkill(ApiModel):
    name: str
    description: str = ""                       # first sentence of the skill's front-matter description
    enabled: bool = True                        # on for the asked session


class ChatSkillList(ApiModel):
    skills: list[ChatSkill]                     # the kb's whitelist (`[agent] skills`), in config order
    session: str | None = None                  # the session the flags are for (none: every skill shows as on)


class ChatSkillsPut(ApiModel):
    enabled: list[str] = Field(description="skill names to turn on; names outside the whitelist are dropped")
