"""The MCP wiring: each tool is one `Library` method. Needs the `mcp` package (>= 2), imported only when serving."""
from __future__ import annotations

import functools

from kb_distillery.kb_mcp.library import KbMcpError, Library

INSTRUCTIONS = (
    "Local knowledge bases curated by the user (an LLM-wiki of linked pages with their sources). To answer a question: "
    "find_kb or search first, then get_page on the best hits, and cite the pages (kb + page) you used. list_kbs shows "
    "every kb. Read-only."
)


def build(library: Library):
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError as e:
        raise SystemExit("distill mcp needs the `mcp` package (version 2 or newer): pip install 'mcp>=2,<3'") from e

    server = MCPServer("kb-distillery", instructions=INSTRUCTIONS)

    def tool(fn):
        """Register `fn`, turning a library error into a tool error the client sees as text."""
        @functools.wraps(fn)
        def run(*a, **kw):
            try:
                return fn(*a, **kw)
            except KbMcpError as e:
                raise ToolError(str(e)) from None
        return server.tool()(run)

    @tool
    def list_kbs() -> dict:
        """List every local knowledge base: id, title, description, page and source counts, last change."""
        return library.list_kbs()

    @tool
    def find_kb(question: str, limit: int = 3) -> dict:
        """Find which knowledge bases can answer a question, ranked, each with its best-matching pages. Use this first when you do not know which kb to look in."""
        return library.find_kb(question, limit)

    @tool
    def search(query: str, kb: str | None = None, limit: int = 10) -> dict:
        """Full-text search over wiki pages (all kbs, or one by id). Returns kb, page, title, description and a snippet; open hits with get_page."""
        return library.search(query, kb, limit)

    @tool
    def get_index(kb: str, section: str | None = None) -> str:
        """Return a kb's wiki/index.md (its sections); pass `section` (e.g. `person`) for that section's page list."""
        return library.get_index(kb, section)

    @tool
    def get_page(kb: str, page: str) -> str:
        """Return one wiki page (frontmatter + markdown). `page` is the path or file name from search/get_index, a slug, or the title."""
        return library.get_page(kb, page)

    @tool
    def get_sources(kb: str, page: str, max_chars: int = 2000) -> dict:
        """Return the raw sources a page cites: path, manifest disposition, size and, for text files, the first `max_chars` characters (0 = metadata only)."""
        return library.get_sources(kb, page, max_chars)

    @tool
    def whats_new(since: str | None = None, kb: str | None = None, limit: int = 20) -> dict:
        """Recent knowledge steps (log.md entries or kb(op) commits), newest first. `since` is YYYY-MM-DD (default: last 30 days)."""
        return library.whats_new(since, kb, limit)

    return server
