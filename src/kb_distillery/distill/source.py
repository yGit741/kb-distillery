"""Read think sources and distilled page sections."""
import os

from kb_distillery.config.paths import vault_root

from .paths import think_abs
ROOT = vault_root()


def _strip_frontmatter(text):
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\n")


def read_think_body(think_rel):
    path = think_abs(think_rel)
    text = open(path, encoding="utf-8").read()
    body = _strip_frontmatter(text)
    if "<!-- human-zone -->" in text:
        body = text.split("<!-- human-zone -->", 1)[1].split("<!-- end-human-zone -->", 1)[0]
    return body.strip()


def read_think_body_from_file(rel):
    path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    body = _strip_frontmatter(text)
    if "<!-- human-zone -->" in text:
        body = text.split("<!-- human-zone -->", 1)[1].split("<!-- end-human-zone -->", 1)[0]
    return body.strip()


def extract_section(text, heading):
    marker = f"## {heading}"
    if marker not in text:
        return ""
    _, rest = text.split(marker, 1)
    lines = []
    for line in rest.splitlines()[1:]:
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def read_summary(distilled_rel):
    path = os.path.join(ROOT, distilled_rel)
    if not os.path.isfile(path):
        return ""
    return extract_section(open(path, encoding="utf-8").read(), "Summary")
