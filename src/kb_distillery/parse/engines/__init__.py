"""Parser engines. An engine turns some pages of a PDF into one record per page; `run.py` windows, resumes and stores.

    class Engine:  name: str;  parse(pdf, pages, workdir) -> {1-based page: record}

A record is the engine's own per-page JSON (kept as the resume cache) and `markdown(record)` renders it.
Engines never read or write a knowledge base: `workdir` is a scratch directory the caller owns."""
from __future__ import annotations

from typing import Protocol


class EngineError(RuntimeError):
    """The engine could not parse the window; the message carries the exact failure."""


class Engine(Protocol):
    name: str

    def parse(self, pdf: str, pages: list, workdir: str) -> dict: ...

    def markdown(self, record: dict) -> str: ...

    def figures(self, record: dict, width: float, height: float) -> list: ...   # image boxes in points
