"""Fenix — SQLite persistence for the world-class layer.

WAL-mode SQLite for the newer subsystems (sessions, ratings, rate limits,
brain health, embeddings, conversations). Older JSON stores (accounts,
projects, memory, evolution) keep their tested atomic-write paths.

One connection per thread (Flask threaded mode); WAL allows readers and
writers to proceed concurrently. All access goes through row helpers below.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time

from store import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "fenix.sqlite3")
_local = threading.local()


def _key(token: str | None) -> str:
    """Stable per-user key without storing the raw token."""
    return hashlib.sha256(str(token or "").encode()).hexdigest()[:32]


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.conn = c
    return c


def _init() -> None:
    c = conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_key TEXT NOT NULL,
            conversation_id TEXT,
            message TEXT NOT NULL,
            reply TEXT NOT NULL,
            rating INTEGER NOT NULL,           -- 1 up, -1 down
            reason TEXT DEFAULT '',
            brain TEXT DEFAULT '',
            created REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_key, created);

        CREATE TABLE IF NOT EXISTS rate_limits (
            key TEXT PRIMARY KEY,
            window_start REAL NOT NULL,
            count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brain_health (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL,
            checked_at REAL NOT NULL,
            detail TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            user_key TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            vector TEXT NOT NULL,              -- JSON array of floats
            created REAL NOT NULL,
            PRIMARY KEY (user_key, entry_id)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_key TEXT NOT NULL,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            created REAL NOT NULL,
            updated REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_key, updated DESC);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
        """
    )
    c.commit()


_init()


# --------------------------- Ratings (data flywheel) ---------------------------

def add_rating(user_token: str, conversation_id: str | None, message: str,
               reply: str, rating: int, reason: str = "", brain: str = "") -> dict:
    c = conn()
    c.execute(
        "INSERT INTO ratings (user_key, conversation_id, message, reply, rating, reason, brain, created)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (_key(user_token), conversation_id or "", (message or "")[:4000], (reply or "")[:12000],
         1 if rating >= 0 else -1, (reason or "")[:500], brain[:40], time.time()),
    )
    c.commit()
    return {"ok": True}


def rating_stats() -> dict:
    c = conn()
    up = c.execute("SELECT COUNT(*) n FROM ratings WHERE rating=1").fetchone()["n"]
    down = c.execute("SELECT COUNT(*) n FROM ratings WHERE rating=-1").fetchone()["n"]
    return {"up": up, "down": down, "total": up + down}


def export_training_pairs(min_score: int = 0, user_token: str | None = None) -> list[dict]:
    """Rated pairs for a LoRA round (up-rated only by default).

    Scoped to one account when a token is given. It used to ignore the owner
    and return every rating in the database, which only stayed safe because
    the route in front of it required an admin — a leak waiting for the next
    caller.
    """
    c = conn()
    if user_token is not None:
        rows = c.execute(
            "SELECT message, reply, rating, created FROM ratings"
            " WHERE rating >= ? AND user_key=? ORDER BY created",
            (min_score, _key(user_token)),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT message, reply, rating, created FROM ratings"
            " WHERE rating >= ? ORDER BY created",
            (min_score,),
        ).fetchall()
    return [{"instruction": r["message"], "output": r["reply"], "rating": r["rating"],
             "created": r["created"]} for r in rows]


# --------------------------- Rate limiting ---------------------------

def rate_limit(key: str, limit: int, window_s: int) -> tuple[bool, int, int]:
    """Fixed-window limiter. Returns (allowed, remaining, retry_after_s)."""
    now = time.time()
    c = conn()
    with c:
        row = c.execute("SELECT window_start, count FROM rate_limits WHERE key=?", (key,)).fetchone()
        if row is None or now - row["window_start"] >= window_s:
            c.execute(
                "INSERT INTO rate_limits (key, window_start, count) VALUES (?,?,1)"
                " ON CONFLICT(key) DO UPDATE SET window_start=excluded.window_start, count=1",
                (key, now),
            )
            return True, limit - 1, 0
        count = row["count"] + 1
        if count > limit:
            retry = int(window_s - (now - row["window_start"])) + 1
            return False, 0, retry
        c.execute("UPDATE rate_limits SET count=? WHERE key=?", (count, key))
        return True, limit - count, 0


# --------------------------- Brain health ---------------------------

def set_brain_health(state: str, detail: str = "") -> None:
    c = conn()
    with c:
        c.execute(
            "INSERT INTO brain_health (id, state, checked_at, detail) VALUES (1,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET state=excluded.state, checked_at=excluded.checked_at,"
            " detail=excluded.detail",
            (state[:20], time.time(), detail[:300]),
        )


def get_brain_health() -> dict | None:
    row = conn().execute("SELECT state, checked_at, detail FROM brain_health WHERE id=1").fetchone()
    if row is None:
        return None
    return {"state": row["state"], "checked_at": row["checked_at"], "detail": row["detail"]}


# --------------------------- Conversations ---------------------------

def _new_id() -> str:
    return secrets.token_urlsafe(9)


def create_conversation(user_token: str, title: str = "") -> dict:
    cid = _new_id()
    now = time.time()
    c = conn()
    with c:
        c.execute(
            "INSERT INTO conversations (id, user_key, title, created, updated) VALUES (?,?,?,?,?)",
            (cid, _key(user_token), (title or "New chat")[:80], now, now),
        )
    return {"id": cid, "title": (title or "New chat")[:80]}


def list_conversations(user_token: str) -> list[dict]:
    rows = conn().execute(
        "SELECT id, title, summary, created, updated FROM conversations"
        " WHERE user_key=? ORDER BY updated DESC LIMIT 100",
        (_key(user_token),),
    ).fetchall()
    return [{"id": r["id"], "title": r["title"], "summary": r["summary"],
             "updated": r["updated"]} for r in rows]


def rename_conversation(user_token: str, conversation_id: str, title: str) -> bool:
    c = conn()
    with c:
        cur = c.execute(
            "UPDATE conversations SET title=? WHERE id=? AND user_key=?",
            ((title or "").strip()[:80] or "New chat", conversation_id, _key(user_token)),
        )
    return cur.rowcount > 0


def delete_conversation(user_token: str, conversation_id: str) -> bool:
    c = conn()
    with c:
        cur = c.execute("DELETE FROM conversations WHERE id=? AND user_key=?",
                        (conversation_id, _key(user_token)))
        c.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    return cur.rowcount > 0


def append_message(user_token: str, conversation_id: str, role: str, content: str) -> bool:
    c = conn()
    with c:
        owns = c.execute("SELECT 1 FROM conversations WHERE id=? AND user_key=?",
                         (conversation_id, _key(user_token))).fetchone()
        if not owns:
            return False
        c.execute("INSERT INTO messages (conversation_id, role, content, created) VALUES (?,?,?,?)",
                  (conversation_id, "user" if role == "user" else "assistant", (content or "")[:16000], time.time()))
        c.execute("UPDATE conversations SET updated=? WHERE id=?", (time.time(), conversation_id))
    return True


def get_messages(user_token: str, conversation_id: str, limit: int = 200) -> list[dict]:
    c = conn()
    owns = c.execute("SELECT 1 FROM conversations WHERE id=? AND user_key=?",
                     (conversation_id, _key(user_token))).fetchone()
    if not owns:
        return []
    rows = c.execute(
        "SELECT role, content, created FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
        (conversation_id, max(1, min(limit, 400))),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"], "created": r["created"]}
            for r in reversed(rows)]


def set_summary(user_token: str, conversation_id: str, summary: str) -> None:
    c = conn()
    with c:
        c.execute("UPDATE conversations SET summary=? WHERE id=? AND user_key=?",
                  ((summary or "")[:2000], conversation_id, _key(user_token)))


def get_summary(user_token: str, conversation_id: str) -> str:
    row = conn().execute("SELECT summary FROM conversations WHERE id=? AND user_key=?",
                         (conversation_id, _key(user_token))).fetchone()
    return (row["summary"] if row else "") or ""


# --------------------------- Semantic memory ---------------------------

def store_embedding(user_token: str, entry_id: str, vector: list[float]) -> None:
    c = conn()
    with c:
        c.execute(
            "INSERT INTO embeddings (user_key, entry_id, vector, created) VALUES (?,?,?,?)"
            " ON CONFLICT(user_key, entry_id) DO UPDATE SET vector=excluded.vector,"
            " created=excluded.created",
            (_key(user_token), entry_id, json.dumps([round(float(x), 5) for x in vector]), time.time()),
        )


def all_embeddings(user_token: str) -> dict[str, list[float]]:
    rows = conn().execute("SELECT entry_id, vector FROM embeddings WHERE user_key=?",
                          (_key(user_token),)).fetchall()
    out = {}
    for r in rows:
        try:
            out[r["entry_id"]] = json.loads(r["vector"])
        except Exception:
            continue
    return out


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
