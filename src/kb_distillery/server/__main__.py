"""python -m kb_distillery.server [--port 8765] [--no-open] [--no-build] — the API and the React shell on one port.

Before serving it rebuilds `src/kb_distillery/_webapp` (gitignored build output) when the frontend sources changed."""
import argparse
import os
import sys
import webbrowser

from kb_distillery.server.security import assert_loopback_bind

DEFAULT_PORT = 8765
BLAS_THREAD_VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def limit_blas_threads(environ=None):
    """One BLAS thread for the server process; False when numpy was already imported (the caps no longer apply).

    The graph's similar-to math is a handful of matrix products per snapshot build, run in the warm thread. With
    the default pool (one spinning OpenBLAS thread per core) those products starve the event loop on a busy
    machine: every request waited for minutes at load 8x the cores, and answered in under a second with one
    thread. A value already in the environment is kept. Must run before numpy is first imported."""
    environ = os.environ if environ is None else environ
    for var in BLAS_THREAD_VARS:
        environ.setdefault(var, "1")
    return "numpy" not in sys.modules


def free_port(host: str, wanted: int, tries: int = 10) -> int:
    """`wanted` when it is free, else the next free port (another app instance is the usual reason it is taken)."""
    import socket
    for port in range(wanted, wanted + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
        if port != wanted:
            print(f"port {wanted} is in use (another app instance?); using {port} instead", flush=True)
        return port
    raise SystemExit(f"ports {wanted}-{wanted + tries - 1} are all in use; pass --port")


def main(argv=None):
    if not limit_blas_threads():
        print("note: numpy was imported before the server started; BLAS thread caps not applied", flush=True)
    parser = argparse.ArgumentParser(description="kb-distillery app server")
    parser.add_argument("--port", type=int, default=None,
                        help=f"default {DEFAULT_PORT}, or the next free one when it is taken; a port given here is used as is")
    parser.add_argument("--host", default="127.0.0.1",
                        help="loopback only, unless KB_AUTH=proxy (self-hosting behind an identity-aware proxy)")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    parser.add_argument("--no-build", action="store_true", help="serve src/kb_distillery/_webapp as is (skip the rebuild check)")
    parser.add_argument("--kb", default=None, help="knowledge base id or folder path (else $KB; see `distill kb list`)")
    parser.add_argument("--open-path", default="/app/start", help="the page the browser tab opens (default /app/start)")
    args = parser.parse_args(argv)
    assert_loopback_bind(args.host)
    if not args.open_path.startswith("/"):
        parser.error("--open-path must start with /")
    if args.port is None:
        args.port = free_port(args.host, DEFAULT_PORT)

    import uvicorn
    from kb_distillery.server.app import create_app
    from kb_distillery.server.spa import ensure_app_dist, frontend_dir

    if not args.no_build and frontend_dir() is not None:      # an installed wheel has no sources to check
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
        webbrowser.open(f"{base}{args.open_path}")
    from kb_distillery.graph.cache import start_refresher
    start_refresher()                 # warm the graph snapshot in a daemon thread and keep it fresh (KB_GRAPH_WARM=0: off)
    # proxy_headers=False: the ASGI client stays the TCP peer, never an X-Forwarded-For value (the trusted-header
    # check in security.authenticate depends on it)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning", proxy_headers=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
