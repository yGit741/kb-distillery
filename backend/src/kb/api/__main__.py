"""python -m kb.api [--port 8765] [--no-open] [--no-build] — the API, the legacy pages and the React shell on one port.

Before serving it rebuilds `frontend/dist` (gitignored build output) when the frontend sources changed."""
import argparse
import webbrowser

from kb.api.security import assert_loopback_bind

DEFAULT_PORT = 8765


def main(argv=None):
    parser = argparse.ArgumentParser(description="Thesis KB app server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1", help="loopback only")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    parser.add_argument("--no-build", action="store_true", help="serve frontend/dist as is (skip the rebuild check)")
    args = parser.parse_args(argv)
    assert_loopback_bind(args.host)

    import uvicorn
    from kb.api.app import create_app
    from kb.api.spa import ensure_app_dist

    if not args.no_build:
        print("frontend/dist: checking sources…", flush=True)
        state = ensure_app_dist()
        print(f"frontend/dist: {state}", flush=True)

    base = f"http://{args.host}:{args.port}"
    for name, path in (("app", "/app"), ("start", "/start"), ("graph", "/graph"), ("explore", "/explore"),
                       ("pipeline", "/pipeline"), ("lifecycle", "/lifecycle"), ("ops", "/ops"),
                       ("chat", "/chat"), ("api docs", "/docs")):
        print(f"{name:<11} {base}{path}")
    print("(Ctrl+C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(f"{base}/start")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
