"""Storage connectors: how a knowledge base reaches its raw sources. See `kb_distillery.storage.base` for the interface and
`meta-defaults/docs/storage.md` for how a kb picks one."""
from .base import SHORT_SHA1, AuthStatus, Connector, NotFound, ObjectInfo, StorageError, check_key
from .registry import connector_names, for_kb, load_class

__all__ = ["SHORT_SHA1", "AuthStatus", "Connector", "NotFound", "ObjectInfo", "StorageError", "check_key",
           "connector_names", "for_kb", "load_class"]
