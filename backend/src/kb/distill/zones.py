"""Parse human/agent zones in think pages."""
import os
import sys

from kb.core.schema import (  # noqa: E402
    AGENT_ZONE_END,
    AGENT_ZONE_START,
    HUMAN_ZONE_END,
    HUMAN_ZONE_START,
)


def extract_zone(text, start, end):
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def human_zone(text):
    return extract_zone(text, HUMAN_ZONE_START, HUMAN_ZONE_END)


def agent_zone(text):
    return extract_zone(text, AGENT_ZONE_START, AGENT_ZONE_END)


def replace_agent_zone(text, new_body):
    if AGENT_ZONE_START not in text or AGENT_ZONE_END not in text:
        raise ValueError("think page missing agent zone markers")
    before = text.split(AGENT_ZONE_START, 1)[0]
    after = text.split(AGENT_ZONE_END, 1)[1]
    body = new_body.strip()
    return f"{before}{AGENT_ZONE_START}\n{body}\n{AGENT_ZONE_END}{after}"


def has_zones(text):
    return all(m in text for m in (HUMAN_ZONE_START, HUMAN_ZONE_END, AGENT_ZONE_START, AGENT_ZONE_END))
