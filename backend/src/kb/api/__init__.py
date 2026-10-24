"""The typed HTTP API (FastAPI). Start with `python -m kb.api`; see README.md for adding a router."""
from kb.api.app import create_app

__all__ = ["create_app"]
