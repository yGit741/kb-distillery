"""Seed the demo kb's local state with proposals of every producer and class, so every proposals screen and variant has
something to show: `pixi run demo-proposals` (= `python -m kb_distillery.proposals demo --kb examples/demo`).

The story: Dana, the demo's owner, is turning her clinical NLP notes into a thesis chapter while she job-hunts. She
asks the page chat to soften a claim and check it against a paper, flags two sentences while reading, drops a new paper
in, lets the nightly lint tidy front matter, merges two pages that grew into one topic, splits a long notes page,
extracts a section into its own page, and looks back at one fix she undid and one chat edit she turned down. Her
Ingest screen shows one row in each group: a paper still being read, one waiting for her review, one she applied and
one she rejected, and two that did not finish.

Fixtures only: no model call, no network. Writes nothing but `<kb>/.local/` (proposals, flags, ingest jobs, one chat thread) and
never applies a proposal, so the tracked pages stay as they are. Idempotent: every seeded record carries a fixed
`de00...` id; a run removes the previous seed and writes it again.
"""
from __future__ import annotations

import contextlib
import datetime
import glob
import json
import os

from kb_distillery.proposals import flags as page_flags
from kb_distillery.proposals import restructure, service, store
from kb_distillery.proposals.model import ProposalError
from kb_distillery.services import ingest_ui
from kb_distillery.vault import links

PREFIX = "de00"
THREAD = "skill-clinical-nlp"


@contextlib.contextmanager
def _local_writes():
    """The demo is read-only by design (it lives under the engine's examples/): proposals can be shown, not applied.
    Seeding writes only `.local/`, so the read-only check is lifted for the seed calls and nothing else."""
    saved = service._writable
    service._writable = service._root
    try:
        yield
    finally:
        service._writable = saved


def _page(root, slug):
    with open(os.path.join(root, "wiki", f"{slug}.md"), encoding="utf-8") as f:
        return f.read()


def _swap(text, before, after):
    if before not in text:
        raise ProposalError(409, f"demo fixture is out of date: {before[:40]!r} is not on the page")
    return text.replace(before, after, 1)


def _stamp(hours_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    return t.isoformat(timespec="seconds")


def clear(root) -> None:
    """Remove a previous seed: the `de00` proposals, flags and chat messages; everything else stays."""
    for p in glob.glob(os.path.join(store.folder(root), f"{PREFIX}*.json")):
        os.remove(p)
    for p in glob.glob(os.path.join(root, ".local", "flags", "*.json")):
        with open(p, encoding="utf-8") as f:
            rows = json.load(f)
        keep = [r for r in rows if not str(r.get("id", "")).startswith(PREFIX)]
        if len(keep) != len(rows):
            page_flags._save(root, os.path.basename(p)[:-5], keep)
    path = os.path.join(root, ".local", "chat", f"{THREAD}.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            msgs = json.load(f).get("messages") or []
        _write_thread(root, [m for m in msgs if not m.get("demo")])
    for p in glob.glob(os.path.join(root, ".local", ingest_ui.LOCAL_SUBDIR, f"{PREFIX}*.json")):
        os.remove(p)


def _write_thread(root, messages):
    path = os.path.join(root, ".local", "chat", f"{THREAD}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"messages": messages}, f, indent=1)


def _fix(root, made, n, hours_ago, **extra):
    """Give a just-created proposal its fixed id and an earlier timestamp (the inbox timeline needs a spread)."""
    pid = f"{PREFIX}{n:04x}"
    p = store.load(root, made["id"])
    os.remove(store.path(root, made["id"]))
    p.update(id=pid, created=_stamp(hours_ago), updated=_stamp(hours_ago), **extra)
    store.save(root, p)
    return pid


def _proposals(root):
    """[(n, hours_ago, create(), extra fields)]: the seeded proposals, oldest last."""
    nlp = _page(root, "skill-clinical-nlp")
    torch = _page(root, "skill-pytorch")
    design = _page(root, "skill-system-design")
    paper = "negation-aware-clinical-ner"
    paper_text = (
        "---\ntype: article\nlayer: source\ndepth: easy\nmaturity: digested\n"
        'description: "A benchmark study of clinical entity recognition with negation: models that ignore negation '
        'over-report findings, most on rare conditions."\n---\n\n'
        "# Negation-aware clinical NER\n\n"
        "## Key claims\n"
        "- Ignoring negation (\"no sign of pneumonia\") is the largest single error source in the studied systems.\n"
        "- Rare conditions are where evaluation sets are thinnest; the study reports wide confidence intervals there.\n"
        f"- Relevant to {links.link('skill-clinical-nlp', 'Clinical NLP')}.\n")
    chat_text = _swap(nlp, "evaluation on rare dangerous cases.",
                      "and evaluation, which is hardest on rare conditions where test sets are small.")
    chat_text = _swap(chat_text, "Read recent clinical NER benchmarks",
                      "Read recent clinical NER benchmarks (start with the negation-aware NER study)")
    ingest_nlp = _swap(nlp, "## Gap\n", f"## Reading\n- {links.link(paper, 'Negation-aware clinical NER')}\n\n## Gap\n")
    flags_text = _swap(torch, "Revise pinned memory, worker start-up cost and collate functions.",
                       "Revise pinned memory and worker start-up cost; collate functions matter only for ragged batches.")
    typo_text = _swap(design, "Next step after", "The next step after")
    rejected = _swap(nlp, "Language-model work on medical free text",
                     "State-of-the-art language-model work on medical free text")
    return [
        (1, 2, lambda: service.create(
            "Chat: soften the evaluation claim, check against the negation paper",
            [{"kind": "edit_page", "slug": "skill-clinical-nlp", "new_text": chat_text, "sources": [paper],
              "reason": "the paper reports wide intervals on rare conditions, not a general danger claim"}],
            producer={"kind": "chat", "instruction": "soften this, check against @negation-aware-clinical-ner",
                      "context": {"message": "soften this, check against @negation-aware-clinical-ner",
                                  "mentions": [paper], "selections": [{"block_at": 3, "text": "rare dangerous cases"}]}},
            root=root), {}),
        (2, 5, lambda: service.create(
            "Fix 1 flagged passage in skill-pytorch",
            [{"kind": "edit_page", "slug": "skill-pytorch", "new_text": flags_text,
              "reason": "collate functions only matter for variable-length batches"}],
            producer={"kind": "flags", "instruction": "too broad: collate is only an issue for ragged batches",
                      "context": {"flag_ids": [], "slug": "skill-pytorch"}}, root=root), {}),
        (3, 9, lambda: service.create(
            "Ingest: Negation-aware clinical NER",
            [{"kind": "create_page", "slug": paper, "text": paper_text, "reason": "new source"},
             {"kind": "edit_page", "slug": "skill-clinical-nlp", "new_text": ingest_nlp, "reason": "link the new paper"}],
            producer={"kind": "ingest", "instruction": "ingest raw/papers/negation-aware-clinical-ner.pdf",
                      "context": {"source": "raw/papers/negation-aware-clinical-ner.pdf", "tier": "easy",
                                  "collection": ""}},
            note="tier easy", root=root), {}),
        (4, 20, lambda: service.create(
            "Suggested fix (maturity): skill-clinical-nlp",
            [{"kind": "set_frontmatter", "slug": "skill-clinical-nlp", "key": "maturity", "value": "growing",
              "reason": "the page now cites a source and has a reading list"}],
            producer={"kind": "lint", "instruction": "maturity is behind the page",
                      "context": {"finding": "maturity", "key": "maturity", "slugs": ["skill-clinical-nlp"],
                                  "detail": "seed page with sources"}},
            note="nightly suggestion", root=root), {}),
        (5, 30, lambda: restructure.merge(["skill-ml-ops", "skill-system-design"], "skill-system-design",
                                          root=root), {}),
        (6, 34, lambda: restructure.split("notes-acme-technical-interview", [7], ["Acme interview takeaways"],
                                          root=root), {}),
        (7, 40, lambda: restructure.extract("dana-levi", 6, 7, "Dana Levi skills overview", root=root), {}),
        (8, 52, lambda: service.create(
            "Typo: system design next step",
            [{"kind": "edit_page", "slug": "skill-system-design", "new_text": typo_text, "reason": "wording"}],
            producer={"kind": "manual", "instruction": "small wording fix"}, root=root),
         {"status": "undone", "applied": {"at": _stamp(51), "pages": ["skill-system-design"], "hunks": None,
                                          "commit": None, "auto": True},
          "undone": {"at": _stamp(50), "commit": None}}),
        (9, 60, lambda: service.create(
            "Chat: call it state of the art",
            [{"kind": "edit_page", "slug": "skill-clinical-nlp", "new_text": rejected, "reason": "stronger opening"}],
            producer={"kind": "chat", "instruction": "make the opening stronger",
                      "context": {"message": "make the opening stronger", "mentions": [], "selections": []}},
            root=root), {"status": "rejected"}),
        (10, 70, lambda: service.create(
            "Ingest: Calibration of clinical risk scores",
            [{"kind": "edit_page", "slug": "skill-system-design", "new_text": typo_text, "reason": "link the new paper"}],
            producer={"kind": "ingest", "instruction": "ingest raw/papers/calibration-of-clinical-risk-scores.pdf",
                      "context": {"source": "raw/papers/calibration-of-clinical-risk-scores.pdf", "tier": "full",
                                  "collection": ""}},
            note="tier full", root=root),
         {"status": "applied", "applied": {"at": _stamp(68), "pages": ["skill-system-design"], "hunks": None,
                                           "commit": None, "auto": False}}),
        (11, 80, lambda: service.create(
            "Ingest: A survey of federated learning",
            [{"kind": "edit_page", "slug": "skill-clinical-nlp", "new_text": rejected, "reason": "link the new paper"}],
            producer={"kind": "ingest", "instruction": "ingest https://example.org/federated-learning-survey",
                      "context": {"source": "raw/web-clips/federated-learning-survey.html", "tier": "easy",
                                  "collection": ""}},
            note="tier easy", root=root), {"status": "rejected"}),
    ]


def _ingests():
    """[(n, hours_ago, source, kind, tier, status, failed step, error, proposal number)]: the Ingest screen's rows."""
    return [
        (1, 0.05, "https://example.org/rare-disease-nlp", "url", "full", "running", "digest", None, None),
        (2, 9, "negation-aware-clinical-ner.pdf", "file", "easy", "done", None, None, 3),
        (3, 70, "calibration-of-clinical-risk-scores.pdf", "file", "full", "done", None, None, 10),
        (4, 80, "https://example.org/federated-learning-survey", "url", "easy", "done", None, None, 11),
        (5, 26, "https://example.org/missing-page", "url", "easy", "failed", "fetch", "that address could not be found", None),
        (6, 100, "interview-notes.pdf", "file", "full", "interrupted", "convert", "the server stopped while this was running", None),
    ]


def _write_ingests(root):
    d = os.path.join(root, ".local", ingest_ui.LOCAL_SUBDIR)
    os.makedirs(d, exist_ok=True)
    ids = []
    for n, hours, source, kind, tier, status, at, error, prop in _ingests():
        jid = f"{PREFIX}{n:04x}"
        t = datetime.datetime.now(datetime.timezone.utc).timestamp() - hours * 3600
        steps = []
        for name in ingest_ui.STEPS:
            state = "done" if status == "done" else "pending"
            if status != "done" and at:
                state = "done" if ingest_ui.STEPS.index(name) < ingest_ui.STEPS.index(at) else ("failed" if name == at else "pending")
            if name == "fetch" and kind == "file":
                state = "skipped"
            steps.append({"name": name, "state": state, "detail": ""})
        if status == "running":
            steps[1]["state"], steps[2]["state"] = "done", "active"
            steps[2]["detail"] = "reading with the default backend"
        rec = {"id": jid, "status": status, "source": source, "kind": kind, "tier": tier, "collection": "", "backend": "",
               "steps": steps, "proposal_id": f"{PREFIX}{prop:04x}" if prop else None,
               "pages": ["skill-clinical-nlp"] if prop else [], "error": error, "created": t,
               "finished": None if status == "running" else t + 40, "demo": True}
        with open(os.path.join(d, jid + ".json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        ids.append(jid)
    return ids


FLAGS = [
    ("skill-clinical-nlp", "prepare one example about annotation guidelines", "the thesis chapter needs two examples, not one"),
    ("skill-clinical-nlp", "named entities, negation, summarisation", "add de-identification; the chapter depends on it"),
    ("skill-pytorch", "collate functions", "too broad: collate is only an issue for ragged batches"),
]


def seed(root) -> dict:
    """Write the demo seed under `<root>/.local/` (removing a previous one first); returns {proposals, flags}."""
    root = os.path.realpath(root)
    clear(root)
    ids = []
    with _local_writes():
        for n, hours, make, extra in _proposals(root):
            ids.append(_fix(root, make(), n, hours, **extra))
    ingest_ids = _write_ingests(root)
    flag_ids = []
    for i, (slug, text, note) in enumerate(FLAGS, 1):
        row = page_flags.add(slug, text, note, root=root)
        rows = page_flags._load(root, slug)
        fid = f"{PREFIX}{i:04x}"
        for r in rows:
            if r["id"] == row["id"]:
                r["id"] = fid
        page_flags._save(root, slug, rows)
        flag_ids.append(fid)
    path = os.path.join(root, ".local", "chat", f"{THREAD}.json")
    msgs = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            msgs = json.load(f).get("messages") or []
    ask = "soften this, check against @negation-aware-clinical-ner"
    msgs += [{"role": "user", "text": ask, "at": _stamp(2), "demo": True,
              "selections": [{"block_at": 3, "text": "rare dangerous cases"}], "mentions": ["negation-aware-clinical-ner"]},
             {"role": "assistant", "demo": True, "at": _stamp(2), "proposal_id": f"{PREFIX}0001", "hunks": 2,
              "skipped": [], "unknown_mentions": [],
              "text": "The paper supports a narrower claim: evaluation is hardest on rare conditions. I proposed two edits."}]
    _write_thread(root, msgs)
    return {"proposals": ids, "flags": flag_ids, "ingests": ingest_ids}
