"""The old stdlib dashboard, served behind the FastAPI app as a catch-all.

`kb.dashboard.serve.Handler` keeps answering every old page and `/api/*` name the typed routers do not
(yet) own. It runs on a private loopback port inside this process, started on first use, and requests are
forwarded byte for byte (method, query, Origin, body), responses streamed back — so the chat SSE keeps
streaming and a closed tab still reaches the handler as a broken pipe. Delete a legacy route by giving its
path to a router; delete this module when the last page is ported.
"""
import threading
from http.server import ThreadingHTTPServer

import httpx
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import StreamingResponse

HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailers", "upgrade", "content-length"}
FORWARD_HEADERS = ("content-type", "origin", "accept", "accept-language", "cache-control", "if-none-match")


class LegacyBridge:
    def __init__(self):
        self._lock = threading.Lock()
        self._server = None
        self._client = None
        self.base = None

    def _start(self):
        with self._lock:
            if self._server is None:
                from kb.dashboard.serve import Handler   # lazy: heavy imports, legacy only
                self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                self._server.daemon_threads = True
                threading.Thread(target=self._server.serve_forever, name="kb-legacy", daemon=True).start()
                self.base = f"http://127.0.0.1:{self._server.server_address[1]}"
                self._client = httpx.AsyncClient(base_url=self.base, timeout=None)
        return self._client

    async def forward(self, request: Request, path: str | None = None) -> StreamingResponse:
        client = self._start()
        target = path if path is not None else request.url.path
        if request.url.query:
            target += "?" + request.url.query
        headers = {k: v for k, v in request.headers.items() if k in FORWARD_HEADERS}
        body = await request.body() if request.method in ("POST", "PUT", "PATCH", "DELETE") else None
        upstream = await client.send(client.build_request(request.method, target, headers=headers, content=body),
                                     stream=True)
        out = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
        return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code, headers=out,
                                 background=BackgroundTask(upstream.aclose))

    async def close(self):
        with self._lock:
            server, client, self._server, self._client = self._server, self._client, None, None
        if client:
            await client.aclose()
        if server:
            server.shutdown()
            server.server_close()
