"""The typed HTTP API (FastAPI). Start with `python -m kb_distillery.server`; see README.md for adding a router."""
from kb_distillery.server.app import create_app

__all__ = ["create_app"]
