"""Stdlib HTTP server for the vault health dashboard."""
import argparse
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.lint.lint import collect_snapshot
from kb_distillery.dashboard.render import render_page
from kb_distillery.services.graph import build_graph_snapshot
from kb_distillery.services.pipeline import build_digestion_snapshot
from kb_distillery.services.lifecycle import build_lifecycle_snapshot
from kb_distillery.api.assets import STATIC_DIR, THUMB_WIDTH, VIZ_REPORTER, thumbnail_png
from kb_distillery.dashboard.shell import inject_nav
from kb_distillery.publish.site.state import share_log_tail, share_state
from kb_distillery.services import pages as explore_data
from kb_distillery.services import chat as chat_data
from kb_distillery.services import corpus as corpus_data
from kb_distillery.services import scopes as scopes_data
from kb_distillery.services import chat_agent
from kb_distillery.dashboard import ops_routes

GRAPH_HTML = os.path.join(os.path.dirname(__file__), "graph.html")
DIGESTION_HTML = os.path.join(os.path.dirname(__file__), "digestion.html")
EXPLORE_HTML = os.path.join(os.path.dirname(__file__), "explore.html")
LIFECYCLE_HTML = os.path.join(os.path.dirname(__file__), "lifecycle.html")
START_HTML = os.path.join(os.path.dirname(__file__), "start.html")
CHAT_HTML = os.path.join(os.path.dirname(__file__), "chat.html")
MAX_POST_BYTES = 4 * 1024 * 1024
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
RAW_TYPES = {**IMAGE_TYPES, ".pdf": "application/pdf", ".md": "text/plain; charset=utf-8",
             ".txt": "text/plain; charset=utf-8", ".json": "text/plain; charset=utf-8",
             ".html": "text/plain; charset=utf-8", ".eml": "text/plain; charset=utf-8"}
DEFAULT_PORT = 8765
SCOPE_POST = {"/api/scope/resolve": lambda p: scopes_data.resolve_nodes(p.get("nodes")),
              "/api/scope/save": scopes_data.save_scope,
              "/api/scope/delete": scopes_data.delete_scope,
              "/api/scope/duplicate": scopes_data.duplicate_scope}


def safe_raw_path(rel):
    """Absolute path of a file under raw/, or None — no traversal, no symlink escape."""
    raw_root = os.path.realpath(os.path.join(ROOT, "raw"))
    full = os.path.realpath(os.path.join(ROOT, rel or ""))
    if not (rel or "").startswith("raw/") or not full.startswith(raw_root + os.sep):
        return None
    return full if os.path.isfile(full) else None


def share_status():
    return share_state()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if ops_routes.handles(path) and ops_routes.handle(self, path, query):
            return
        if path.startswith("/api/explore/"):
            self._explore_api(path[len("/api/explore/"):], query)
            return
        if path == "/vault-asset":
            full = explore_data.resolve_asset((query.get("name") or [""])[0])
            if not full:
                self.send_error(404)
                return
            with open(full, "rb") as f:
                body = f.read()
            self._respond(200, body, IMAGE_TYPES.get(os.path.splitext(full)[1].lower(), "application/octet-stream"))
            return
        if path == "/raw-file":
            self._raw_file((query.get("path") or [""])[0])
            return
        if path == "/raw-thumb":
            self._raw_thumb((query.get("path") or [""])[0], (query.get("w") or [THUMB_WIDTH])[0])
            return
        if path == "/chat-asset":
            full = explore_data.resolve_chat_asset((query.get("path") or [""])[0])
            if not full:
                self.send_error(404)
                return
            with open(full, "rb") as f:
                body = f.read()
            ext = os.path.splitext(full)[1].lower()
            if ext == ".html":  # report height so the sandboxed iframe can size itself
                body = body.replace(b"</body>", VIZ_REPORTER + b"</body>") if b"</body>" in body \
                    else body + VIZ_REPORTER
            self._respond(200, body, {".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
                                      ".png": "image/png"}[ext])
            return
        if path in ("/explore", "/explore.html"):
            with open(EXPLORE_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "explore").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/health":
            snap = collect_snapshot(quiet=True)
            snap.pop("_rows", None)
            body = json.dumps(snap, indent=2).encode("utf-8")
            self._respond(200, body, "application/json")
            return
        if path == "/api/schema":
            from kb_distillery.services.schema import schema_payload
            self._respond(200, json.dumps(schema_payload()).encode("utf-8"), "application/json")
            return
        if path == "/api/graph":
            layer = (query.get("layer") or [""])[0]
            snap = build_graph_snapshot(layer="raw" if layer == "raw" else None)
            body = json.dumps(snap).encode("utf-8")
            self._respond(200, body, "application/json")
            return
        if path == "/api/corpus":
            data = corpus_data.build_corpus((query.get("format") or [""])[0])
            if data is None:
                self._json(400, {"error": "unknown format", "formats": list(corpus_data.FORMATS)})
            else:
                self._json(200, data)
            return
        if path == "/api/raw-preview":
            data, err = corpus_data.build_preview((query.get("path") or [""])[0])
            self._json(400, {"error": err}) if err else self._json(200, data)
            return
        if path == "/api/citations":
            self._json(200, corpus_data.build_citations())
            return
        if path in ("/api/pipeline", "/api/digestion"):        # /digestion kept as an alias
            snap = build_digestion_snapshot()
            body = json.dumps(snap).encode("utf-8")
            self._respond(200, body, "application/json")
            return
        if path == "/api/scopes":
            self._json(200, scopes_data.list_scopes())
            return
        if path == "/api/scope":
            data = scopes_data.get_scope((query.get("slug") or [""])[0])
            self._json(404, {"error": "unknown scope"}) if data is None else self._json(200, data)
            return
        if path == "/api/share/status":
            self._respond(200, json.dumps(share_status()).encode("utf-8"), "application/json")
            return
        if path == "/share-log":
            self._respond(200, share_log_tail().encode("utf-8"), "text/plain; charset=utf-8")
            return
        if path == "/api/lifecycle":
            snap = build_lifecycle_snapshot()
            body = json.dumps(snap).encode("utf-8")
            self._respond(200, body, "application/json")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            safe = os.path.normpath(rel)
            if safe.startswith(".."):
                self.send_error(403)
                return
            fpath = os.path.join(STATIC_DIR, safe)
            if os.path.isfile(fpath):
                if fpath.endswith(".css"):
                    ctype = "text/css"
                else:
                    ctype = "application/javascript"
                with open(fpath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)
            return
        if path in ("/", "/index.html"):
            snap = collect_snapshot(quiet=True)
            snap.pop("_rows", None)
            html = render_page(snap).encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/graph", "/graph.html"):
            with open(GRAPH_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "graph").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/scopes", "/scopes.html"):
            with open(os.path.join(os.path.dirname(__file__), "scopes.html"), encoding="utf-8") as f:
                html = inject_nav(f.read(), "scopes").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/pipeline", "/digestion", "/digestion.html"):
            with open(DIGESTION_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "pipeline").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/start", "/start.html"):
            with open(START_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "start").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/lifecycle", "/lifecycle.html"):
            with open(LIFECYCLE_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "lifecycle").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path in ("/chat", "/chat.html"):
            with open(CHAT_HTML, encoding="utf-8") as f:
                html = inject_nav(f.read(), "chat").encode("utf-8")
            self._respond(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/chat/status":
            self._json(200, chat_data.status())
            return
        if path == "/api/chat/prompts":
            self._json(200, {"prompts": chat_data.list_prompts()})
            return
        self.send_error(404)

    # ── Chat (POST) ────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        # Same-origin guard: only the dashboard page itself may post (no cross-site form posts).
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            self._json(403, {"error": "cross-origin request refused"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_POST_BYTES:
                raise ValueError("bad length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "expected a JSON body"})
            return
        if path == "/api/raw-action":
            result, err = corpus_data.run_action(payload.get("action"), payload.get("path"))
            self._json(400, {"error": err}) if err else self._json(200, result)
        elif path in SCOPE_POST:
            try:
                self._json(200, SCOPE_POST[path](payload))
            except scopes_data.ScopeError as e:
                self._json(e.status, {"error": str(e)})
        elif path == "/api/chat":
            self._chat(payload)
        elif path == "/api/chat/save":
            try:
                rel = chat_data.save_chat(payload)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            print(f"chat saved → {rel}", flush=True)
            self._json(200, {"path": rel})
        elif path == "/api/chat/settings":
            try:
                chat_data.save_settings(payload)
            except (ValueError, TypeError) as e:
                self._json(400, {"error": str(e)})
                return
            except OSError as e:
                self._json(500, {"error": f"cannot write settings: {e}"})
                return
            self._json(200, chat_data.status())
        elif path in ("/api/chat/keys", "/api/chat/keys/remove"):
            # the key never leaves this process: stored under ~/.config/kb-distillery/keys/<name>
            try:
                if path.endswith("/remove"):
                    chat_data.remove_key(payload.get("name"))
                    if chat_data.load_settings().get("active_key") == payload.get("name"):
                        chat_data.save_settings({"active_key": ""})
                else:
                    entry = chat_data.add_key(payload.get("name"), payload.get("key"))
                    chat_data.save_settings({"active_key": entry["name"], "auth_mode": "api_key"})
            except (ValueError, TypeError) as e:
                self._json(400, {"error": str(e)})
                return
            except OSError as e:
                self._json(500, {"error": f"cannot write key: {e}"})
                return
            self._json(200, chat_data.status())
        else:
            self.send_error(404)

    def _chat(self, payload):
        settings = chat_data.load_settings()
        auth_mode = payload.get("auth_mode") or settings["auth_mode"]
        if auth_mode not in chat_data.AUTH_MODES:
            self._json(400, {"error": f"unknown auth_mode {auth_mode!r}"})
            return
        backend = payload.get("backend") or settings["backend"]
        if backend not in chat_data.BACKENDS:
            self._json(400, {"error": f"unknown backend {backend!r}"})
            return
        if auth_mode == "subscription":
            if backend != "agent":
                self._json(400, {"error": "the subscription works with the Agent backend only",
                                 "hint": "switch Backend to Agent, or pick an API key"})
                return
            sub = chat_agent.subscription_status()
            if not sub["logged_in"]:
                self._json(400, {"error": "Claude subscription not available",
                                 "hint": sub["error"] or "run `claude login` in a terminal"})
                return
            key = None
        else:
            if payload.get("active_key"):
                settings = {**settings, "active_key": payload["active_key"]}
            key, _ = chat_data.load_api_key(settings)
            if not key:
                self._json(400, {"error": "no API key", "hint":
                                 "add one in the Session card, create "
                                 f"{chat_data.KEY_FILE} (read on every message) "
                                 f"or start the dashboard with ANTHROPIC_API_KEY set"})
                return
        question = (payload.get("question") or "").strip()
        if not question:
            self._json(400, {"error": "empty question"})
            return
        model = payload.get("model") if payload.get("model") in chat_data.MODEL_IDS else chat_data.DEFAULT_MODEL
        history = [m for m in (payload.get("history") or []) if isinstance(m, dict)]
        scope = None
        scope_slug = (payload.get("scope") or "").strip() if isinstance(payload.get("scope"), str) else ""
        if scope_slug:
            from kb_distillery.core import scopes as scope_lib
            try:
                scope = scope_lib.scope_context(scope_slug, chat_data.ROOT)
            except scope_lib.ScopeUnknown as exc:
                self._json(400, {"error": str(exc)})
                return
        if backend == "agent":
            self._chat_agent(payload, key, model, question, history,
                             billing="subscription" if key is None else "api", scope=scope)
        else:
            self._chat_direct(payload, key, model, question, history, scope=scope)

    def _sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def event(name, data):
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))
            self.wfile.flush()
        return event

    def _chat_agent(self, payload, key, model, question, history, billing="api", scope=None):
        """Read-only research agent over the Claude Agent SDK (src/kb_distillery/services/chat_agent.py).
        key=None + billing="subscription" runs on the `claude login` account."""
        info = chat_agent.sdk_info()
        if not info["available"]:
            self._json(400, {"error": "agent backend unavailable",
                             "hint": f"{info['error']}; or switch the backend to Direct"})
            return
        system = chat_agent.build_agent_system(payload.get("system") or "", scope=scope)
        event = self._sse_start()
        gen = chat_agent.stream_agent(question, model=model, system=system, key=key, billing=billing,
                                      session_id=payload.get("session") or None, history=history, scope=scope)
        try:
            for name, data in gen:
                if name == "ping":
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                if name == "tool":
                    print(f"  tool {data.get('summary')}{' (error)' if data.get('error') else ''}", flush=True)
                elif name == "usage":
                    print(f"chat agent {model}: turns={data.get('num_turns')} "
                          f"cost=${data.get('cost_usd') or 0:.4f} ({data.get('duration_ms')} ms)", flush=True)
                event(name, data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the tab was closed or Stop was pressed; closing the generator interrupts the agent
        finally:
            gen.close()

    def _chat_direct(self, payload, key, model, question, history, scope=None):
        """One Messages call with the top retrieved pages pasted in (the original chat)."""
        hits, new_slugs = chat_data.plan_turn(history, question, scope=scope)
        system = chat_data.build_system(payload.get("system") or "", scope=scope)
        messages = chat_data.build_messages(history, question, new_slugs)
        event = self._sse_start()
        try:
            event("sources", {"hits": hits, "new": new_slugs})
            for kind, value in chat_data.stream_claude(system, messages, model, key):
                if kind == "text":
                    event("delta", value)
                    continue
                cost = chat_data.record_usage(model, value)
                event("usage", {**value, "model": model, "cost_usd": cost,
                                "spend": chat_data.spend_summary()})
                print(f"chat {model}: in={value.get('input_tokens')} "
                      f"cache_write={value.get('cache_creation_input_tokens')} "
                      f"cache_read={value.get('cache_read_input_tokens')} "
                      f"out={value.get('output_tokens')} cost=${cost:.4f}", flush=True)
            event("done", {})
        except chat_data.ChatError as e:
            event("error", {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the tab was closed or Stop was pressed

    def _json(self, code, data):
        self._respond(code, json.dumps(data).encode("utf-8"), "application/json")

    def _explore_api(self, name, query):
        def arg(key):
            return (query.get(key) or [""])[0]

        if name == "index":
            data = explore_data.build_index()
        elif name == "page":
            data = explore_data.build_page(arg("slug"))
        elif name == "search":
            lim = arg("limit")
            data = explore_data.search(arg("q"), min(int(lim), 5000) if lim.isdigit() else 40)
        elif name == "path":
            data = explore_data.find_paths(arg("a"), arg("b"))
        else:
            data = None
        if data is None:
            self._respond(404, b'{"error": "not found"}', "application/json")
            return
        self._respond(200, json.dumps(data).encode("utf-8"), "application/json")

    def _raw_file(self, rel):
        """Serve one file under raw/ for the pipeline preview pane (read-only)."""
        full = safe_raw_path(rel)
        if not full:
            self.send_error(404)
            return
        ctype = RAW_TYPES.get(os.path.splitext(full)[1].lower())
        if not ctype:
            self.send_error(415)
            return
        with open(full, "rb") as f:
            body = f.read()
        self._respond(200, body, ctype)

    def _raw_thumb(self, rel, width=THUMB_WIDTH):
        """Page-1 PNG of a raw PDF for the hover preview; images are served as-is."""
        full = safe_raw_path(rel)
        if not full:
            self.send_error(404)
            return
        ext = os.path.splitext(full)[1].lower()
        if ext in IMAGE_TYPES:
            self._raw_file(rel)
            return
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = THUMB_WIDTH
        png = thumbnail_png(full, width) if ext == ".pdf" else None
        if not png:
            self.send_error(415)
            return
        self._respond(200, png, "image/png")

    def _respond(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Thesis wiki health dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    args = parser.parse_args(argv)

    base = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"start       {base}/start")
    print(f"health      {base}/")
    print(f"graph       {base}/graph")
    print(f"explore     {base}/explore")
    print(f"pipeline    {base}/pipeline")
    print(f"lifecycle   {base}/lifecycle")
    print(f"ops         {base}/ops")
    print(f"chat        {base}/chat  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(f"{base}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    return 0
