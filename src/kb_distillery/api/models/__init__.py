"""Pydantic response/request models, one module per resource (`models/<resource>.py`).
Convention: subclass `ApiModel`; name the top-level model `<Resource>...` (HealthSnapshot, LifecycleSnapshot)."""
from kb_distillery.api.models.base import ApiModel

__all__ = ["ApiModel"]
