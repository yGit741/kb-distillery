"""The typed HTTP API (FastAPI). Start with `python -m kb_distillery.api`; see README.md for adding a router."""
from kb_distillery.api.app import create_app

__all__ = ["create_app"]
