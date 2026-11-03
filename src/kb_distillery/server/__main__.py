"""python -m kb_distillery.server [--port 8765] [--no-open] [--no-build] — the API and the React shell on one port.

Before serving it rebuilds `src/kb_distillery/_webapp` (gitignored build output) when the frontend sources changed."""
import argparse
import webbrowser

from kb_distillery.server.security import assert_loopback_bind

DEFAULT_PORT = 8765


def main(argv=None):
    parser = argparse.ArgumentParser(description="kb-distillery app server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1", help="loopback only")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    parser.add_argument("--no-build", action="store_true", help="serve src/kb_distillery/_webapp as is (skip the rebuild check)")
    parser.add_argument("--kb", default=None, help="knowledge base id or folder path (else $KB; see `distill kb list`)")
    args = parser.parse_args(argv)
    assert_loopback_bind(args.host)

    import uvicorn
    from kb_distillery.server.app import create_app
    from kb_distillery.server.spa import ensure_app_dist

    if not args.no_build:
        print("src/kb_distillery/_webapp: checking sources…", flush=True)
        state = ensure_app_dist()
        print(f"src/kb_distillery/_webapp: {state}", flush=True)

    base = f"http://{args.host}:{args.port}"
    for name, path in (("app", "/app"), ("start", "/app/start"), ("graph", "/app/graph"), ("pages", "/app/pages"),
                       ("pipeline", "/app/pipeline"), ("lifecycle", "/app/lifecycle"), ("system", "/app/system"),
                       ("chat", "/app/chat"), ("api docs", "/docs")):
        print(f"{name:<11} {base}{path}")
    print("(Ctrl+C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(f"{base}/app/start")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
