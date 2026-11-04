"""Live agent turns: queue a message into a running turn, or interrupt it (the chat transcript PR).

A running turn registers a `Live` under its session id; `POST /api/chat/message` calls `send()`, which writes the
text to the live SDK client as the next user message (streaming input mode) instead of restarting the turn.
`send` returns False when no turn is live (finished, or the client is closed): the caller then stops and resumes
the session with a normal request. All state is in-process; nothing here touches the vault.
"""
import asyncio
import threading

_LIVE = {}
_LOCK = threading.Lock()


class Live:
    """One turn's handle. `emit` is the turn's event sink (a `(event, data)` callable, thread-safe)."""

    def __init__(self, emit):
        self.emit = emit
        self.client = None
        self.loop = None
        self.pending = 0
        self.closed = False
        self._lock = threading.Lock()

    def attach(self, client, loop):
        self.client, self.loop = client, loop

    def send(self, text):
        """Queue `text` as the next user message. False when the turn is over or not connected yet."""
        with self._lock:
            if self.closed or self.client is None or self.loop is None:
                return False
            self.pending += 1
            client, loop = self.client, self.loop
        # outside the lock: the runner's `take_pending` runs on the loop and must not wait for us
        try:
            fut = asyncio.run_coroutine_threadsafe(client.query(text), loop)
            fut.result(timeout=10)
        except Exception:
            with self._lock:
                self.pending = max(0, self.pending - 1)
            return False
        self.emit(("user", {"text": text}))
        return True

    def take_pending(self):
        """Runner side: is another queued message waiting for its turn? With none, the handle closes."""
        with self._lock:
            if self.pending > 0:
                self.pending -= 1
                return True
            self.closed = True
            return False

    def interrupt(self):
        """Ask the CLI to stop the current turn now (the Stop button); a no-op when not connected."""
        with self._lock:
            client, loop = self.client, self.loop
        if client is None or loop is None or self.closed:
            return
        try:
            asyncio.run_coroutine_threadsafe(client.interrupt(), loop)
        except Exception:
            pass


def register(session, live):
    if session:
        with _LOCK:
            _LIVE[session] = live


def unregister(live):
    with _LOCK:
        for k in [k for k, v in _LIVE.items() if v is live]:
            del _LIVE[k]


def send(session, text):
    with _LOCK:
        live = _LIVE.get(session)
    return bool(live and text and live.send(text))
