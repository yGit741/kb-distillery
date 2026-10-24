"""Validate distill plan.json."""
VALID_ACTIONS = {
    "append_threads",
    "append_papers",
    "update_section",
    "append_related",
}


def validate_plan(data):
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object")
    for key in ("source", "distilled_at", "touches", "proposals"):
        if key not in data:
            raise ValueError(f"plan missing {key!r}")
    if not isinstance(data["proposals"], list):
        raise ValueError("proposals must be a list")
    for i, p in enumerate(data["proposals"]):
        if not isinstance(p, dict):
            raise ValueError(f"proposal {i} must be an object")
        action = p.get("action")
        if action not in VALID_ACTIONS:
            raise ValueError(f"proposal {i}: unknown action {action!r}")
        if not p.get("target"):
            raise ValueError(f"proposal {i}: missing target")
    return True
