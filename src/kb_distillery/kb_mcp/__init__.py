"""kb-mcp: a read-only MCP server (stdio) that lets any Claude session read the local knowledge bases.

    distill mcp [--kb <id|path>]…        serve the bases dir ($KB_DISTILLERY_HOME) plus every --kb folder

`library.py` is the plain-Python read model (no MCP import; unit-tested on a fixture kb), `server.py` registers its
functions as MCP tools. Only `wiki/` is served, plus the `raw/` files a page cites (`get_sources`); `think/` never.
"""
