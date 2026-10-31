"""Copy the local metrics store to a Cloudflare D1 database (SQLite) — the long-run home of the numbers.

    pixi run metrics -- d1 init        create the `kb-metrics` database once (wrangler) and save its id
    pixi run metrics -- d1 push [--dry-run]   upsert sessions + golden runs (idempotent)

Auth is the publisher's cloud account (`Publisher.account_api()`; the Cloudflare one: CLOUDFLARE_API_TOKEN, else wrangler's OAuth token); the
database id lives in meta/ops/sync.toml `[metrics] d1_database_id`. Only numbers and labels are sent —
never prompt text, replies, diffs or file contents (`first_prompt` stays local).
"""
import json
import os
import re

from kb.metrics import store
from kb.paths import vault_root

DB_NAME = "kb-metrics"
SYNC_TOML = os.path.join("meta", "ops", "sync.toml")
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, start TEXT, minutes REAL, branch TEXT,
       task TEXT, golden TEXT, skills TEXT, human_turns INT, calls INT, subagents INT, first_context INT,
       main_in INT, main_cw INT, main_cr INT, main_out INT, sub_in INT, sub_cw INT, sub_cr INT, sub_out INT,
       models TEXT, usd REAL)""",
    """CREATE TABLE IF NOT EXISTS golden_runs (run TEXT, task TEXT, label TEXT, v INT, kind TEXT, sha TEXT,
       model TEXT, effort TEXT, started TEXT, ok INT, passed INT, usd REAL, turns INT, minutes REAL,
       first_context INT, subagents INT, judge_score REAL, judge_pass INT, judge_flagged INT, judge_usd REAL,
       checks_ok INT, checks_n INT, diff_lines INT, PRIMARY KEY (run, task, started))""",
]
SESSION_COLS = ["id", "start", "minutes", "branch", "task", "golden", "skills", "human_turns", "calls", "subagents",
                "first_context", "main_in", "main_cw", "main_cr", "main_out", "sub_in", "sub_cw", "sub_cr",
                "sub_out", "models", "usd"]
GOLDEN_COLS = ["run", "task", "label", "v", "kind", "sha", "model", "effort", "started", "ok", "passed", "usd",
               "turns", "minutes", "first_context", "subagents", "judge_score", "judge_pass", "judge_flagged",
               "judge_usd", "checks_ok", "checks_n", "diff_lines"]
MAX_PARAMS = 100   # D1 binds at most 100 values per statement


def session_row(r):
    m, s = r["main"], r["sub"]
    return [r["id"], r.get("start"), r.get("minutes"), r.get("branch"), r["task"], r.get("golden"),
            ",".join(r.get("skills", [])), r.get("human_turns"), r.get("calls"), r.get("subagents"),
            r.get("first_context"), m["in"], m["cw"], m["cr"], m["out"], s["in"], s["cw"], s["cr"], s["out"],
            json.dumps({k: sum(v.values()) for k, v in r.get("models", {}).items()}), r.get("usd")]


def golden_row(r):
    j, checks = r.get("judge") or {}, r.get("checks") or []
    return [r["run"], r["task"], r.get("label"), r.get("v"), r.get("kind"), r.get("sha"), r.get("model"),
            r.get("effort"), r.get("started"), int(bool(r.get("ok"))), int(bool(r.get("passed"))), r.get("usd"),
            r.get("turns"), r.get("minutes"), r.get("first_context"), r.get("subagents"), j.get("score"),
            int(bool(j.get("pass"))), int(bool(j.get("flagged"))), j.get("usd"),
            sum(1 for c in checks if c.get("ok")), len(checks), r.get("diff_lines")]


def upserts(table, cols, rows):
    """(sql, params) batches of multi-row INSERT OR REPLACE."""
    per = max(1, MAX_PARAMS // len(cols))
    for i in range(0, len(rows), per):
        chunk = rows[i:i + per]
        marks = ",".join("(" + ",".join("?" * len(cols)) + ")" for _ in chunk)
        yield f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES {marks}", [v for row in chunk for v in row]


def database_id(root=None):
    try:
        text = open(os.path.join(root or vault_root(), SYNC_TOML), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'^d1_database_id\s*=\s*"([0-9a-f-]+)"', text, re.M)
    return m.group(1) if m else None


def _account():
    """The publisher's cloud account API (D1 lives in the same Cloudflare account as the site); raises PublishError
    when no publisher is configured or it has none."""
    from kb import publish
    return publish.current().account_api()


def _query(db, sql, params):
    api = _account()
    return api.rest("POST", f"/accounts/{api.account_id}/d1/database/{db}/query", {"sql": sql, "params": params})


def init(root=None):
    """Create the database (or find it) and record its id in meta/ops/sync.toml `[metrics]`."""
    db = database_id(root)
    if db:
        print(f"d1: {DB_NAME} already configured ({db})")
        return 0
    api = _account()
    found = [d for d in api.rest("GET", f"/accounts/{api.account_id}/d1/database").get("result") or []
             if d.get("name") == DB_NAME]
    db = found[0]["uuid"] if found else \
        api.rest("POST", f"/accounts/{api.account_id}/d1/database", {"name": DB_NAME})["result"]["uuid"]
    with open(os.path.join(root or vault_root(), SYNC_TOML), "a", encoding="utf-8") as f:
        f.write(f'\n# Agent metrics (kb.metrics.d1): numbers only, no prompt text.\n[metrics]\nd1_database_id = "{db}"\n')
    for sql in SCHEMA:
        _query(db, sql, [])
    print(f"d1: {DB_NAME} ready ({db}); id saved in {SYNC_TOML}")
    return 0


def push(root=None, dry_run=False):
    sessions = [session_row(r) for r in store.read("sessions.jsonl", root)]
    golden = [golden_row(r) for r in store.read("golden.jsonl", root)]
    stmts = [(s, []) for s in SCHEMA] + list(upserts("sessions", SESSION_COLS, sessions)) \
        + list(upserts("golden_runs", GOLDEN_COLS, golden))
    if dry_run:
        print(f"[dry-run] {len(sessions)} sessions, {len(golden)} golden runs in {len(stmts)} statements")
        return 0
    db = database_id(root)
    if not db:
        print("no D1 database yet — run `pixi run metrics -- d1 init` once")
        return 1
    for sql, params in stmts:
        _query(db, sql, params)
    print(f"d1: {len(sessions)} sessions, {len(golden)} golden runs upserted into {DB_NAME}")
    return 0
