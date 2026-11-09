"""Performance bench: what the user feels on localhost.

    pixi run perf -- [--kb ID|PATH] [--url URL] [--idle N] [--no-browser] [--out FILE]

Server half: start a fresh server on a free port (so the first request is cold), time every endpoint the app shell
hits (cold, then three warm repeats, median), wait `--idle` seconds and time a "reopen" round. Browser half
(Playwright via node, skipped with `--no-browser` or when it is not installed): open /app, then click every top-level
tab twice; the second pass is the tab-switch number. Writes `.cache/perf/<stamp>.json` and prints a compact table.
`--url` benches an already running server instead (nothing is started, so "cold" is only as cold as that server)."""
import argparse
import glob
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ENDPOINTS = ["/app", "/api/kb", "/api/kb/list", "/api/graph", "/api/health", "/api/ops", "/api/pages", "/api/pipeline",
             "/api/lifecycle", "/api/flags", "/api/chat/status", "/api/scopes"]
WARM_REPEATS = 3
REQUEST_TIMEOUT = 180
TOP_KEYS = ("kb", "pages", "server_ms", "browser_ms", "env")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch(url):
    """One GET: {ms, bytes, status}. Never raises: a failure is a status of 0 / the HTTP code."""
    t0 = time.perf_counter()
    status, body = 0, b""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Origin": url.split("/", 3)[0] + "//" + url.split("/")[2]}),
                                    timeout=REQUEST_TIMEOUT) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read()
    except Exception:
        pass
    return {"ms": round((time.perf_counter() - t0) * 1000), "bytes": len(body), "status": status}, body


def bench_endpoints(base, idle):
    out = {}
    pages = None
    for ep in ENDPOINTS:
        cold, body = fetch(base + ep)
        if ep == "/api/pages" and cold["status"] == 200:
            try:
                data = json.loads(body)
                pages = len(data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), []))
            except Exception:
                pass
        warm = [fetch(base + ep)[0] for _ in range(WARM_REPEATS)]
        out[ep] = {"cold_ms": cold["ms"], "warm_ms": int(statistics.median(w["ms"] for w in warm)),
                   "bytes": cold["bytes"], "status": cold["status"]}
    if idle:
        time.sleep(idle)
        for ep in ENDPOINTS:
            out[ep]["reopen_ms"] = fetch(base + ep)[0]["ms"]
    return out, pages


def find_playwright():
    env = os.environ.get("PLAYWRIGHT_MODULE")
    cands = [env] if env else []
    cands += sorted(glob.glob(os.path.expanduser("~/.npm/_npx/*/node_modules/playwright")))
    return next((c for c in cands if c and os.path.isdir(c)), None)


def bench_browser(base):
    pw, node = find_playwright(), shutil.which("node")
    if not pw or not node:
        return {"skipped": "playwright (node) not found; set PLAYWRIGHT_MODULE"}
    try:
        p = subprocess.run([node, str(Path(__file__).with_name("browser.mjs")), pw, base, "{}"], capture_output=True, text=True,
                           timeout=1800)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"skipped": f"browser run failed: {type(e).__name__}: {e}"}


def listeners():
    try:
        p = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=10)
        return sorted({" ".join(line.split()[:1] + line.split()[-2:-1]) for line in p.stdout.splitlines() if "python" in line.lower()})
    except Exception:
        return []


def start_server(kb):
    port = free_port()
    env = dict(os.environ, KB_SHARE_AUTODEPLOY="0")
    if kb:
        env["KB"] = kb
    proc = subprocess.Popen([sys.executable, "-m", "kb_distillery.server", "--port", str(port), "--no-open", "--no-build"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 120:
        if proc.poll() is not None:
            raise RuntimeError("server exited during start")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc, port, round((time.perf_counter() - t0) * 1000)
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not listen within 120 s")


def run(kb=None, url=None, idle=0, browser=True):
    proc = None
    notes = {"load_avg": [round(x, 2) for x in os.getloadavg()], "listeners_before": listeners(), "mode": "attached" if url else "fresh-server",
             "idle_s": idle}
    try:
        if url:
            base = url.rstrip("/")
        else:
            proc, port, start_ms = start_server(kb)
            base = f"http://127.0.0.1:{port}"
            notes["server_start_ms"] = start_ms
        server_ms, pages = bench_endpoints(base, idle)
        browser_ms = bench_browser(base) if browser else {"skipped": "--no-browser"}
        notes["load_avg_after"] = [round(x, 2) for x in os.getloadavg()]
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return {"kb": kb or os.environ.get("KB") or os.environ.get("KB_ROOT") or "(default)", "pages": pages,
            "server_ms": server_ms, "browser_ms": browser_ms, "env": notes}


def table(rep):
    lines = [f"kb {rep['kb']}  pages {rep['pages']}  load {rep['env']['load_avg']}",
             f"{'endpoint':<20}{'cold':>8}{'warm':>8}{'reopen':>8}{'bytes':>10}  st"]
    for ep, r in rep["server_ms"].items():
        lines.append(f"{ep:<20}{r['cold_ms']:>8}{r['warm_ms']:>8}{r.get('reopen_ms', '-'):>8}{r['bytes']:>10}  {r['status']}")
    b = rep["browser_ms"]
    if "skipped" in b:
        lines.append(f"browser: skipped ({b['skipped']})")
    else:
        lines.append(f"browser initial load {b['initial']['ms']} ms, {b['initial']['api_requests']} api calls")
        lines.append(f"{'tab':<20}{'pass1 ms':>10}{'api':>5}{'pass2 ms':>10}{'api':>5}")
        for t in b["tabs"]:
            a, c = b["pass1"].get(t, {}), b["pass2"].get(t, {})
            lines.append(f"{t:<20}{a.get('ms', '-'):>10}{a.get('api_requests', '-'):>5}{c.get('ms', '-'):>10}{c.get('api_requests', '-'):>5}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="kb-distillery performance bench")
    ap.add_argument("--kb", default=None, help="kb id or folder (default: the server's default kb)")
    ap.add_argument("--url", default=None, help="bench an already running server instead of starting one")
    ap.add_argument("--idle", type=int, default=0, help="seconds to wait between the warm round and the reopen round")
    ap.add_argument("--no-browser", action="store_true", help="skip the Playwright part")
    ap.add_argument("--out", default=None, help="report path (default .cache/perf/<stamp>.json)")
    a = ap.parse_args(argv)
    rep = run(a.kb, a.url, a.idle, not a.no_browser)
    out = Path(a.out) if a.out else Path(".cache/perf") / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n")
    print(table(rep))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
