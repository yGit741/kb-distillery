"""Commands the System screen shows to the user, written for how they installed kb-distillery.

The ops code writes its fixes as `pixi run <task> -- …` (what a checkout runs). A wheel install has no pixi tasks:
`ops` and `share` exist as `distill ops …` / `distill share …`; every other task (ship, lanes, daily-sync, install-*)
is repository tooling that has no `distill` form there, so no command is shown rather than one that cannot run.
"""
import re

_PIXI = re.compile(r"^pixi run (ops|share) -- (.*)$")


def user_command(cmd, in_checkout):
    """`cmd` as the installed user should see it: unchanged in a checkout, `distill …` when one exists, else ''."""
    if in_checkout or not isinstance(cmd, str) or "pixi run" not in cmd:
        return cmd
    main, sep, comment = cmd.partition("   # ")
    m = _PIXI.match(main.strip())
    if not m:
        return ""
    return f"distill {m.group(1)} {m.group(2)}" + (sep + comment if sep else "")


def localize(node, in_checkout):
    """Rewrite every `fix` / `next` string of an ops snapshot (nested dicts and lists), in place."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("fix", "next") and isinstance(v, str):
                node[k] = user_command(v, in_checkout)
            else:
                localize(v, in_checkout)
    elif isinstance(node, list):
        for v in node:
            localize(v, in_checkout)
    return node
