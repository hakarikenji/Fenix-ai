"""
Fenix — free-tier scaling layer.

Why this exists
---------------
Every always-free inference tier is capped per day (requests/day, tokens/day).
One free key cannot serve a large audience, and buying more keys costs money.
This module makes the free tier far cheaper to consume without changing the
answers users get:

  1. Response cache (SQLite, on disk, survives restarts).
     Identical or near-identical questions are answered from cache and cost
     zero upstream requests. Typical real traffic is highly repetitive, so
     this is the single biggest multiplier.

  2. Quota-aware routing.
     Each provider tracks how much it has been used and how many consecutive
     failures it has. A provider that is rate-limited or broken is skipped
     fast instead of costing a timeout on every request, so the healthy
     providers absorb the load.

  3. Honest stats.
     `stats()` reports real hit rates and per-provider state so the app can
     show measured health rather than optimism.

Nothing here raises. A cache miss simply falls through to the normal chain.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("FENIX_CACHE_DB", "/tmp/fenix-brains-cache.db"))

# Cached answers are only reused when the request shape matches.
_CACHE_TTL = int(os.environ.get("FENIX_CACHE_TTL", str(60 * 60 * 24 * 14)))  # 14 days
_MAX_ROWS = int(os.environ.get("FENIX_CACHE_MAX", "20000"))

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_stats = {"hit": 0, "miss": 0, "store": 0}

# label -> {"fails": int, "used": int, "cooldown_until": float, "last_error": str}
_provider_state: dict[str, dict] = {}


def _db() -> sqlite3.Connection | None:
    global _conn
    if _conn is not None:
        return _conn
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS answer_cache ("
            " key TEXT PRIMARY KEY, system TEXT, user TEXT, answer TEXT,"
            " label TEXT, created_at REAL)"
        )
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS question_seen ("
            " key TEXT PRIMARY KEY, n INTEGER, updated_at REAL)"
        )
        _conn.commit()
        return _conn
    except Exception:
        return None


def _key(system: str, user: str) -> str:
    h = hashlib.sha256()
    h.update((system or "").strip().encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update((user or "").strip().lower().encode("utf-8", "ignore"))
    return h.hexdigest()


def cache_get(system: str, user: str) -> str | None:
    """Return a cached answer, or None. Never raises."""
    conn = _db()
    if conn is None or not (user or "").strip():
        return None
    try:
        with _lock:
            row = conn.execute(
                "SELECT answer, created_at FROM answer_cache WHERE key = ?",
                (_key(system, user),),
            ).fetchone()
        if not row:
            with _lock:
                _stats["miss"] += 1
            return None
        answer, created = row[0], row[1]
        if not answer or (time.time() - created) > _CACHE_TTL:
            with _lock:
                _stats["miss"] += 1
            return None
        with _lock:
            _stats["hit"] += 1
            conn.execute(
                "INSERT INTO question_seen (key, n, updated_at) VALUES (?, 1, ?) "
                "ON CONFLICT(key) DO UPDATE SET n = n + 1, updated_at = excluded.updated_at",
                (_key(system, user), time.time()),
            )
            conn.commit()
        return answer
    except Exception:
        return None


def cache_put(system: str, user: str, answer: str, label: str = "") -> None:
    """Store an answer. Never raises, never stores empty answers."""
    conn = _db()
    if conn is None or not (answer or "").strip() or not (user or "").strip():
        return
    try:
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO answer_cache"
                " (key, system, user, answer, label, created_at) VALUES (?,?,?,?,?,?)",
                (_key(system, user), system or "", user, answer, label, time.time()),
            )
            # Keep the cache bounded; drop the oldest rows first.
            conn.execute(
                "DELETE FROM answer_cache WHERE key NOT IN "
                "(SELECT key FROM answer_cache ORDER BY created_at DESC LIMIT ?)",
                (_MAX_ROWS,),
            )
            conn.commit()
            _stats["store"] += 1
    except Exception:
        pass


def top_repeats(limit: int = 20) -> list[dict]:
    """Most-asked questions — tells the owner what to train/cache first."""
    conn = _db()
    if conn is None:
        return []
    try:
        with _lock:
            rows = conn.execute(
                "SELECT q.user, s.n FROM question_seen s "
                "JOIN answer_cache q ON q.key = s.key "
                "ORDER BY s.n DESC LIMIT ?", (limit,),
            ).fetchall()
        return [{"question": r[0][:160], "times": r[1]} for r in rows]
    except Exception:
        return []


# ------------------------------------------------------------ quota routing --

def provider_ok(label: str) -> bool:
    """False when a provider is in cooldown after real failures."""
    st = _provider_state.get(label)
    if not st:
        return True
    if st.get("cooldown_until", 0) > time.time():
        return False
    return True


def note_success(label: str) -> None:
    st = _provider_state.setdefault(label, {})
    st["fails"] = 0
    st["cooldown_until"] = 0.0
    st["used"] = st.get("used", 0) + 1


# A daily quota does not recover in minutes. Park the provider until the
# next UTC day instead of retrying it all evening.
QUOTA_COOLDOWN = 20 * 60 * 60


def note_failure(label: str, reason: str = "", quota: bool = False) -> None:
    """Back off so one dead provider stops costing timeouts on every request."""
    st = _provider_state.setdefault(label, {})
    st["fails"] = st.get("fails", 0) + 1
    if quota:
        st["cooldown_until"] = time.time() + QUOTA_COOLDOWN
        st["quota_exhausted"] = True
    else:
        st["quota_exhausted"] = False
        delay = min(600, 30 * (2 ** min(st["fails"] - 1, 5)))
        st["cooldown_until"] = time.time() + delay
    st["last_error"] = reason[:120]


def ordered_labels(labels: list[str]) -> list[str]:
    """Healthy providers first, then those in cooldown, least-used first."""
    live = [l for l in labels if provider_ok(l)]
    cold = [l for l in labels if not provider_ok(l)]
    live.sort(key=lambda l: _provider_state.get(l, {}).get("fails", 0))
    cold.sort(key=lambda l: _provider_state.get(l, {}).get("cooldown_until", 0))
    return live + cold


def stats() -> dict:
    total = _stats["hit"] + _stats["miss"]
    conn = _db()
    size = 0
    if conn is not None:
        try:
            with _lock:
                size = conn.execute("SELECT COUNT(*) FROM answer_cache").fetchone()[0]
        except Exception:
            size = 0
    return {
        "cache_entries": size,
        "hits": _stats["hit"],
        "misses": _stats["miss"],
        "hit_rate": round(_stats["hit"] / total, 3) if total else 0.0,
        "served_from_cache": _stats["hit"],
        "providers": {
            label: {
                "used": st.get("used", 0),
                "fails": st.get("fails", 0),
                "available": provider_ok(label),
                "quota_exhausted": bool(st.get("quota_exhausted")),
                "last_error": st.get("last_error", ""),
            }
            for label, st in _provider_state.items()
        },
    }
