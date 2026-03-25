"""
main.py — Hearth Chat Server

FastAPI WebSocket chat server. Messages are stored in SQLite on an ephemeral
dm-crypt encrypted volume. The volume is reformatted on every boot; all messages
are permanently unrecoverable after power-off.

Protocol (all messages are JSON):
  Client → Server:
    {"type": "join", "nick": "<name>"}          — must be first message
    {"type": "msg",  "text": "<content>"}

  Server → Client:
    {"type": "history",  "messages": [...]}     — sent immediately after join
    {"type": "msg",  "nick": ..., "text": ..., "ts": ...}
    {"type": "joined",   "nick": ..., "ts": ...}
    {"type": "left",     "nick": ..., "ts": ...}

  Close codes:
    4000 — protocol error (bad join message, timeout, etc.)
    4001 — nickname already taken
"""

import asyncio
import json
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

DB_PATH      = Path("/srv/cafebox/chat-data/chat.db")
ROOM         = "general"
HISTORY_LIMIT = 100
MESSAGE_TTL  = 86400   # seconds (24 hours)
JOIN_TIMEOUT = 30      # seconds to wait for join message
MAX_NICK_LEN = 24
MAX_MSG_LEN  = 2000


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT    NOT NULL DEFAULT 'general',
                nick TEXT    NOT NULL,
                text TEXT    NOT NULL,
                ts   INTEGER NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_room_ts ON messages (room, ts)"
        )
        conn.commit()


def get_history(room: str = ROOM) -> list[dict]:
    cutoff = int(time.time()) - MESSAGE_TTL
    with _db() as conn:
        rows = conn.execute(
            """SELECT nick, text, ts FROM messages
               WHERE room = ? AND ts >= ?
               ORDER BY ts DESC LIMIT ?""",
            (room, cutoff, HISTORY_LIMIT),
        ).fetchall()
    return [
        {"type": "msg", "nick": r["nick"], "text": r["text"], "ts": r["ts"]}
        for r in reversed(rows)
    ]


def store_message(nick: str, text: str, room: str = ROOM) -> int:
    now    = int(time.time())
    cutoff = now - MESSAGE_TTL
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages (room, nick, text, ts) VALUES (?, ?, ?, ?)",
            (room, nick, text, now),
        )
        conn.execute(
            "DELETE FROM messages WHERE room = ? AND ts < ?",
            (room, cutoff),
        )
        conn.commit()
    return now


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def join(self, nick: str, ws: WebSocket) -> bool:
        """Register nick. Returns False if already taken."""
        async with self._lock:
            if nick in self._connections:
                return False
            self._connections[nick] = ws
            return True

    async def leave(self, nick: str) -> None:
        async with self._lock:
            self._connections.pop(nick, None)

    async def broadcast(self, payload: dict, exclude: Optional[str] = None) -> None:
        text = json.dumps(payload)
        dead: list[str] = []
        for nick, ws in list(self._connections.items()):
            if nick == exclude:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(nick)
        for nick in dead:
            await self.leave(nick)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.websocket("/chat/ws")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    nick: Optional[str] = None

    try:
        # ---- Expect join -----------------------------------------------
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=JOIN_TIMEOUT)
        except asyncio.TimeoutError:
            await ws.close(code=4000, reason="Join timeout")
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.close(code=4000, reason="Invalid JSON")
            return

        if msg.get("type") != "join" or not isinstance(msg.get("nick"), str):
            await ws.close(code=4000, reason="Expected join message")
            return

        nick = msg["nick"].strip()[:MAX_NICK_LEN]
        if not nick:
            await ws.close(code=4000, reason="Nickname cannot be empty")
            return

        if not await manager.join(nick, ws):
            await ws.close(code=4001, reason="Nickname already taken")
            return

        # ---- Send history then notify others ---------------------------
        history = get_history()
        await ws.send_text(json.dumps({"type": "history", "messages": history}))

        await manager.broadcast(
            {"type": "joined", "nick": nick, "ts": int(time.time())},
            exclude=nick,
        )

        # ---- Message loop ----------------------------------------------
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "msg":
                text = str(msg.get("text", "")).strip()[:MAX_MSG_LEN]
                if not text:
                    continue
                ts = store_message(nick, text)
                await manager.broadcast(
                    {"type": "msg", "nick": nick, "text": text, "ts": ts}
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if nick:
            await manager.leave(nick)
            await manager.broadcast(
                {"type": "left", "nick": nick, "ts": int(time.time())}
            )
