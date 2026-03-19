"""Web-based remote display for the countdown timer and logo.

Runs an aiohttp server in a background thread, serving a single HTML page
that replicates the pygame display window. A remote device (e.g. Raspberry Pi
in kiosk mode) can open the page in a browser to show the countdown.

State updates are pushed from the main pygame loop via WebSocket at ~1 Hz.
Crossfade animations are interpolated client-side for smooth 60fps visuals.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass

from aiohttp import web

logger = logging.getLogger(__name__)


@dataclass
class DisplayState:
    state: str  # "IDLE", "DJ_SET", "SHUFFLE"
    remaining_seconds: int
    formatted_time: str
    timer_alpha: int  # 0-255
    logo_alpha: int  # 0-255
    crossfading: bool
    crossfade_duration: float


_HTML_PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shuffle Partey</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #000;
    overflow: hidden;
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  #logo {
    position: absolute;
    max-width: 100vw;
    max-height: 100vh;
    object-fit: contain;
    opacity: 1;
    transition: none;
  }
  #timer {
    position: absolute;
    font-family: "SF Mono", "DejaVu Sans Mono", "Consolas", monospace;
    font-size: min(70vh, 35vw);
    color: #fff;
    opacity: 0;
    transition: none;
    user-select: none;
  }
  #status {
    position: absolute;
    bottom: 8px;
    right: 12px;
    font-family: sans-serif;
    font-size: 12px;
    color: #333;
  }
</style>
</head>
<body>
<img id="logo" src="/logo.png" alt="">
<div id="timer">00:00</div>
<div id="status"></div>
<script>
const logo = document.getElementById('logo');
const timer = document.getElementById('timer');
const status = document.getElementById('status');

let fadeStart = null;
let fadeFrom = { timerAlpha: 0, logoAlpha: 255 };
let fadeTo = { timerAlpha: 0, logoAlpha: 255 };
let fadeDuration = 3.0;
let fading = false;

function setAlpha(timerA, logoA) {
  timer.style.opacity = timerA / 255;
  logo.style.opacity = logoA / 255;
}

function animateFade(ts) {
  if (!fading) return;
  if (!fadeStart) fadeStart = ts;
  const elapsed = (ts - fadeStart) / 1000;
  const t = Math.min(1, elapsed / fadeDuration);
  const ta = fadeFrom.timerAlpha + (fadeTo.timerAlpha - fadeFrom.timerAlpha) * t;
  const la = fadeFrom.logoAlpha + (fadeTo.logoAlpha - fadeFrom.logoAlpha) * t;
  setAlpha(ta, la);
  if (t < 1) requestAnimationFrame(animateFade);
  else fading = false;
}

function onMessage(data) {
  timer.textContent = data.formatted_time;

  if (data.crossfading && !fading) {
    fadeFrom.timerAlpha = parseFloat(timer.style.opacity || 0) * 255;
    fadeFrom.logoAlpha = parseFloat(logo.style.opacity || 1) * 255;
    fadeTo.timerAlpha = data.timer_alpha;
    fadeTo.logoAlpha = data.logo_alpha;
    fadeDuration = data.crossfade_duration;
    fadeStart = null;
    fading = true;
    requestAnimationFrame(animateFade);
  } else if (!data.crossfading) {
    fading = false;
    setAlpha(data.timer_alpha, data.logo_alpha);
  }
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(proto + '//' + location.host + '/ws');
  ws.onopen = () => { status.textContent = ''; };
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = () => {
    status.textContent = 'reconnecting...';
    setTimeout(connect, 2000);
  };
}
connect();
</script>
</body>
</html>
"""


class WebDisplay:
    """Async web server running in a background thread, serving the remote display."""

    def __init__(self, port: int, logo_path: str) -> None:
        self._port = port
        self._logo_path = logo_path
        self._state = DisplayState(
            state="IDLE",
            remaining_seconds=0,
            formatted_time="00:00",
            timer_alpha=0,
            logo_alpha=255,
            crossfading=False,
            crossfade_duration=3.0,
        )
        self._clients: set[web.WebSocketResponse] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._last_json = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/logo.png", self._handle_logo)
        app.router.add_get("/ws", self._handle_ws)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("Web display serving on http://0.0.0.0:%d", self._port)

        # Run forever until the loop is stopped
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=_HTML_PAGE, content_type="text/html")

    async def _handle_logo(self, request: web.Request) -> web.Response:
        if os.path.exists(self._logo_path):
            return web.FileResponse(self._logo_path)
        return web.Response(status=404)

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        logger.info("Web display client connected (%d total)", len(self._clients))

        # Send current state immediately
        await ws.send_str(json.dumps(asdict(self._state)))

        try:
            async for _ in ws:
                pass  # We don't expect messages from the client
        finally:
            self._clients.discard(ws)
            logger.info("Web display client disconnected (%d total)", len(self._clients))
        return ws

    async def _broadcast(self) -> None:
        msg = json.dumps(asdict(self._state))
        dead: list[web.WebSocketResponse] = []
        for ws in self._clients:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def update(self, state: DisplayState) -> None:
        """Push a new state snapshot (called from the main pygame thread)."""
        self._state = state
        new_json = json.dumps(asdict(state))
        if new_json == self._last_json:
            return
        self._last_json = new_json

        if self._loop is not None and self._clients:
            asyncio.run_coroutine_threadsafe(self._broadcast(), self._loop)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2)
