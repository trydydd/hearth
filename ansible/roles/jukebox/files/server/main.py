"""
main.py — Hearth Jukebox Server

FastAPI service that manages a communal song queue. Patrons browse the music
library, submit tracks, and all connected clients hear the same song at the
same position (approximate synchronisation via elapsed-time offset).

Endpoints:
  GET  /jukebox/health        → {"status": "ok"}
  GET  /jukebox/queue         → list of queued tracks
  POST /jukebox/queue         → add track to queue (body: {"path": "...", "nick": "..."})
  GET  /jukebox/now-playing   → current track info with elapsed seconds
  GET  /jukebox/stream        → audio stream (Range request support)
  GET  /jukebox/library       → browse music files (reloaded on fs change)
  POST /jukebox/rescan        → re-scan music directory immediately
  WS   /jukebox/ws            → real-time queue and playback events

WebSocket events (server → client):
  {"type": "state", "now_playing": {...}|null, "queue": [...]}
  {"type": "tick", "elapsed": 42, "duration": 183}

WebSocket events (client → server):
  {"type": "sync"}
  {"type": "enqueue", "path": "relative/path/to/track.mp3", "nick": "alice"}
"""

import asyncio
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from watchfiles import awatch
from mutagen import File as MutagenFile

# ---------------------------------------------------------------------------
# Configuration — paths are configurable via environment variables so that
# the test suite can redirect to temporary directories without editing code.
# ---------------------------------------------------------------------------

MUSIC_ROOT   = Path(os.environ.get("HEARTH_MUSIC_ROOT", "/srv/hearth/music"))
DB_PATH      = Path(os.environ.get("HEARTH_JUKEBOX_DB", "/tmp/hearth-jukebox.db"))
TICK_INTERVAL = 5  # seconds between WebSocket heartbeat ticks

AUDIO_MIME: dict[str, str] = {
    ".mp3":  "audio/mpeg",
    ".ogg":  "audio/ogg",
    ".flac": "audio/flac",
    ".aac":  "audio/aac",
    ".m4a":  "audio/mp4",
    ".wav":  "audio/wav",
    ".opus": "audio/ogg",
}


# ---------------------------------------------------------------------------
# Database — ephemeral SQLite queue in /tmp; lost on reboot by design.
# ---------------------------------------------------------------------------

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                path      TEXT    NOT NULL,
                nick      TEXT    NOT NULL DEFAULT '',
                submitted INTEGER NOT NULL
            )
        """)
        conn.commit()


def db_enqueue(path: str, nick: str) -> dict:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO queue (path, nick, submitted) VALUES (?, ?, ?)",
            (path, nick, now),
        )
        conn.commit()
        row_id = cur.lastrowid
    return {"id": row_id, "path": path, "nick": nick, "submitted": now}


def db_get_queue() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, path, nick, submitted FROM queue ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def db_dequeue_head() -> Optional[dict]:
    """Remove and return the first item in the queue, or None if empty."""
    with _db() as conn:
        row = conn.execute(
            "SELECT id, path, nick, submitted FROM queue ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM queue WHERE id = ?", (row["id"],))
        conn.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# Playback state machine — IDLE or PLAYING.
# ---------------------------------------------------------------------------

class PlaybackState:
    """Thread-safe (asyncio-safe) holder of current playback state."""

    def __init__(self) -> None:
        # now_playing: None → IDLE; dict → PLAYING
        self.now_playing: Optional[dict] = None
        self.elapsed: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def is_playing(self) -> bool:
        return self.now_playing is not None

    async def start_track(self, track: dict) -> None:
        async with self._lock:
            self.now_playing = track
            self.elapsed = 0.0

    async def stop(self) -> None:
        async with self._lock:
            self.now_playing = None
            self.elapsed = 0.0

    async def tick(self) -> tuple[bool, float, float]:
        """Increment elapsed by 1 s. Returns (is_playing, elapsed, duration)."""
        async with self._lock:
            if self.now_playing is None:
                return False, 0.0, 0.0
            self.elapsed += 1.0
            duration = float(self.now_playing.get("duration", 0))
            return True, self.elapsed, duration

    def snapshot(self) -> dict:
        if self.now_playing is None:
            return {"now_playing": None, "elapsed": 0, "duration": 0}
        return {
            "now_playing": self.now_playing,
            "elapsed": int(self.elapsed),
            "duration": self.now_playing.get("duration", 0),
        }


playback = PlaybackState()


# ---------------------------------------------------------------------------
# Music library — loaded once at startup; restart to refresh after uploads.
# ---------------------------------------------------------------------------

def _track_metadata(abs_path: Path) -> dict:
    """Extract metadata from an audio file using mutagen."""
    relative = str(abs_path.relative_to(MUSIC_ROOT))
    title = artist = album = ""
    duration = 0
    try:
        audio = MutagenFile(abs_path, easy=True)
        if audio is not None:
            title  = (audio.get("title",  [""])[0] or "").strip()
            artist = (audio.get("artist", [""])[0] or "").strip()
            album  = (audio.get("album",  [""])[0] or "").strip()
            if hasattr(audio, "info") and hasattr(audio.info, "length"):
                duration = int(audio.info.length)
    except Exception:
        pass
    return {
        "path":     relative,
        "title":    title or abs_path.stem,
        "artist":   artist,
        "album":    album,
        "duration": duration,
    }


def load_library() -> list[dict]:
    """Return metadata for every audio file found under MUSIC_ROOT."""
    tracks: list[dict] = []
    if not MUSIC_ROOT.exists():
        return tracks
    for ext in AUDIO_MIME:
        for f in MUSIC_ROOT.rglob(f"*{ext}"):
            if f.is_file():
                # Resolve to catch symlink traversal before adding to library
                try:
                    f.resolve().relative_to(MUSIC_ROOT.resolve())
                except ValueError:
                    continue
                tracks.append(_track_metadata(f))
    tracks.sort(key=lambda t: t["path"])
    return tracks


# Populated during lifespan startup; reloaded by watch_library() on changes.
LIBRARY: list[dict] = []


async def watch_library() -> None:
    """Reload LIBRARY and notify clients when files change under MUSIC_ROOT."""
    global LIBRARY
    if not MUSIC_ROOT.exists():
        return
    async for _ in awatch(MUSIC_ROOT):
        LIBRARY = await asyncio.to_thread(load_library)
        await hub.broadcast({"type": "library_updated"})


# ---------------------------------------------------------------------------
# WebSocket hub — broadcast to all connected clients.
# ---------------------------------------------------------------------------

class WsHub:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients = [c for c in self._clients if c is not ws]

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


hub = WsHub()


def _state_event() -> dict:
    """Build the full 'state' event payload."""
    snap = playback.snapshot()
    return {
        "type":        "state",
        "now_playing": snap["now_playing"],
        "queue":       db_get_queue(),
    }


# ---------------------------------------------------------------------------
# Playback engine — asyncio background task started with the app lifespan.
# ---------------------------------------------------------------------------

async def playback_engine() -> None:
    """
    One-second loop that:
      - Starts the next queued track when IDLE.
      - Advances elapsed time when PLAYING.
      - Dequeues a finished track and starts the next.
      - Broadcasts tick events every TICK_INTERVAL seconds.
    """
    tick_accumulator = 0
    while True:
        await asyncio.sleep(1)

        if not playback.is_playing:
            head = db_dequeue_head()
            if head is None:
                continue
            abs_path = (MUSIC_ROOT / head["path"]).resolve()
            try:
                abs_path.relative_to(MUSIC_ROOT.resolve())
            except ValueError:
                continue  # Discard invalid path silently
            meta = _track_metadata(abs_path)
            track = {**meta, "nick": head["nick"]}
            await playback.start_track(track)
            await hub.broadcast(_state_event())
            tick_accumulator = 0
            continue

        still_playing, elapsed, duration = await playback.tick()
        if not still_playing:
            continue

        # Track finished — advance to the next.
        if duration > 0 and elapsed >= duration:
            await playback.stop()
            await hub.broadcast(_state_event())
            tick_accumulator = 0
            continue

        # Periodic heartbeat tick.
        tick_accumulator += 1
        if tick_accumulator >= TICK_INTERVAL:
            tick_accumulator = 0
            await hub.broadcast({
                "type":     "tick",
                "elapsed":  int(elapsed),
                "duration": int(duration),
            })


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global LIBRARY
    init_db()
    LIBRARY = load_library()
    tasks = [
        asyncio.create_task(playback_engine()),
        asyncio.create_task(watch_library()),
    ]
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/jukebox/health")
async def health():
    return {"status": "ok"}


@app.get("/jukebox/queue")
async def get_queue():
    return db_get_queue()


@app.post("/jukebox/queue", status_code=201)
async def post_queue(body: dict):
    path = str(body.get("path", "")).strip()
    nick = str(body.get("nick", "")).strip()
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=422)
    abs_path = (MUSIC_ROOT / path).resolve()
    try:
        abs_path.relative_to(MUSIC_ROOT.resolve())
    except ValueError:
        return JSONResponse({"error": "invalid path"}, status_code=422)
    if not abs_path.is_file():
        return JSONResponse({"error": "track not found"}, status_code=404)
    item = db_enqueue(path, nick)
    await hub.broadcast(_state_event())
    return item


@app.get("/jukebox/now-playing")
async def now_playing():
    return playback.snapshot()


@app.get("/jukebox/library")
async def library():
    return LIBRARY


@app.post("/jukebox/rescan")
async def rescan():
    """Re-scan the music directory immediately and notify connected clients."""
    global LIBRARY
    LIBRARY = await asyncio.to_thread(load_library)
    await hub.broadcast({"type": "library_updated"})
    return {"status": "ok", "tracks": len(LIBRARY)}


@app.get("/jukebox/stream")
async def stream(request: Request):
    snap = playback.snapshot()
    if snap["now_playing"] is None:
        return Response(status_code=204)

    rel_path = snap["now_playing"]["path"]
    abs_path = (MUSIC_ROOT / rel_path).resolve()
    try:
        abs_path.relative_to(MUSIC_ROOT.resolve())
    except ValueError:
        return Response(status_code=403)

    if not abs_path.is_file():
        return Response(status_code=404)

    ext = abs_path.suffix.lower()
    content_type = AUDIO_MIME.get(ext, "application/octet-stream")
    file_size = abs_path.stat().st_size

    range_header = request.headers.get("range", "")

    if range_header and range_header.startswith("bytes="):
        try:
            range_spec = range_header[len("bytes="):]
            parts = range_spec.split("-", 1)
            start = int(parts[0]) if parts[0] else 0
            end   = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        except (ValueError, IndexError):
            start, end = 0, file_size - 1

        start = max(0, min(start, file_size - 1))
        end   = max(start, min(end, file_size - 1))
        chunk_len = end - start + 1

        async def _iter_range():
            async with aiofiles.open(abs_path, "rb") as fh:
                await fh.seek(start)
                remaining = chunk_len
                while remaining > 0:
                    data = await fh.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range":  f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(chunk_len),
        }
        return StreamingResponse(
            _iter_range(),
            status_code=206,
            headers=headers,
            media_type=content_type,
        )

    # Full file response
    async def _iter_full():
        async with aiofiles.open(abs_path, "rb") as fh:
            while True:
                chunk = await fh.read(65536)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Accept-Ranges":  "bytes",
        "Content-Length": str(file_size),
    }
    return StreamingResponse(
        _iter_full(),
        status_code=200,
        headers=headers,
        media_type=content_type,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/jukebox/ws")
async def jukebox_ws(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        # Send current state immediately on connect.
        await ws.send_text(json.dumps(_state_event()))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "sync":
                await ws.send_text(json.dumps(_state_event()))

            elif msg_type == "enqueue":
                path = str(msg.get("path", "")).strip()
                nick = str(msg.get("nick", "")).strip()
                if path:
                    abs_path = (MUSIC_ROOT / path).resolve()
                    try:
                        abs_path.relative_to(MUSIC_ROOT.resolve())
                        if abs_path.is_file():
                            db_enqueue(path, nick)
                            await hub.broadcast(_state_event())
                    except ValueError:
                        pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(ws)
