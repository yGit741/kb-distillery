"""Server-sent events over a sync generator of (event, data) — the chat framing, as a helper.

    return sse_response(chat_agent.stream_agent(...))

Frames are `event: <name>\\ndata: <json>\\n\\n`. A `("ping", None)` item (what the chat generators yield on
a quiet stream) and a stretch of `ping_seconds` without items both become an SSE comment (`: ping`).
The generator runs in its own thread; when the client goes away the stream is cancelled and that thread
calls `gen.close()` itself (closing from another thread would race the running generator), so an agent
behind it is interrupted at its next yield.
"""
import asyncio
import json
import threading
from collections.abc import Iterator

from starlette.responses import StreamingResponse

PING_SECONDS = 15.0
PING_FRAME = b": ping\n\n"
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_END = object()


def frame(event, data):
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")


async def sse_frames(gen: Iterator, ping_seconds: float = PING_SECONDS):
    """Async iterator of encoded SSE frames over the sync generator `gen`."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def post(item):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:      # the loop is gone (server shutting down): nobody is listening
            pass

    def pump():
        try:
            for item in gen:
                if stop.is_set():
                    break
                post(item)
        except Exception as exc:  # noqa: BLE001 — surface as an error event, never a broken stream
            post(("error", {"error": str(exc)}))
        finally:
            close = getattr(gen, "close", None)
            if close:
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
            post(_END)

    thread = threading.Thread(target=pump, name="kb-sse", daemon=True)
    thread.start()
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), ping_seconds)
            except asyncio.TimeoutError:
                yield PING_FRAME
                continue
            if item is _END:
                return
            name, data = item
            yield PING_FRAME if name == "ping" else frame(name, data)
    finally:                      # client disconnect cancels us here: tell the pump to stop and close gen
        stop.set()


def sse_response(gen: Iterator, ping_seconds: float = PING_SECONDS) -> StreamingResponse:
    return StreamingResponse(sse_frames(gen, ping_seconds), media_type="text/event-stream", headers=HEADERS)
