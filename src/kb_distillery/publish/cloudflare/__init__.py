"""Share — build a self-contained HTML of the wiki graph + explorer from a git ref and deploy it.

`pixi run share -- <command>`; subcommands register themselves via `kb_distillery.publish.cloudflare.__main__.MODULES`.
Contracts shared by build / deploy / snapshots live in `kb_distillery.publish.cloudflare.contracts`.
"""
