"""
Fenix — server-side generation quota (credit system).

Fenix runs its own open models on limited compute, so the two expensive paths
(Music audio, Video motion) are metered while everything cheap — chat,
research, memory, lyrics, storyboards, stills — stays unlimited.

Design notes that matter:

* The server is the only authority. Nothing here is mirrored in the browser:
  the client never sends a counter, a remaining amount or a window length.
* A credit is *reserved* at the moment the expensive inference is about to be
  called, never when the user merely opens a screen. A request rejected before
  inference (empty prompt, no engine connected, still cooling down) costs
  nothing.
* Reservation is a single `BEGIN IMMEDIATE` transaction, so two tabs, two
  devices or a double click cannot both take the last credit.
* A short cooldown on an identical job (same user, feature and fingerprint)
  stops accidental repeat submissions before they become wasted GPU time.

Everything is configurable from the environment:

    MUSIC_DAILY_CREDITS        credits per MUSIC_CREDIT_WINDOW_HOURS (default 3)
    MUSIC_CLIP_CREDITS         cost of one audio track          (default 1)
    VIDEO_DAILY_CREDITS        credits per VIDEO_CREDIT_WINDOW_HOURS (default 5)
    VIDEO_CLIP_CREDITS         cost of one standard scene clip  (default 1)
    VIDEO_HD_CREDITS           cost of a long / high-res clip  (default 2)
    VIDEO_MAX_DURATION_SECONDS  hard ceiling on one clip        (default 10)
    VIDEO_HD_PIXELS            pixel count that counts as HD   (default 460800)
    *_CREDIT_WINDOW_HOURS      window length in hours          (default 24)
    QUOTA_COOLDOWN_SECONDS     repeat-submission cooldown      (default 5)
    QUOTA_ENABLED              "0" disables metering entirely  (default "1")

Identity is a caller-supplied opaque key (a hash of the account token, or a
hash of the caller's address for signed-out use). This module never sees an
email, a token or anything else that identifies a person.
"""
from __future__ import annotations

import hashlib
import math
import os
import secrets
import sqlite3
import threading
import time

DATA_DIR = os.environ.get("FENIX_DATA_DIR", ".data")
DB_PATH = os.path.join(DATA_DIR, "fenix.sqlite3")

FEATURES = ("music", "video")
DURATION = 24 * 60 * 60

_lock = threading.RLock()
_local = threading.local()


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    return float(_env_int(name, int(default)))


def enabled() -> bool:
    return str(os.environ.get("QUOTA_ENABLED", "1")).strip().lower() not in (
        "0", "false", "off", "no")


def cooldown_s() -> int:
    return max(0, _env_int("QUOTA_COOLDOWN_SECONDS", 5))


def config(feature: str) -> dict:
    """Effective, always-int limits for one feature. No floats reach SQL."""
    feature = (feature or "").lower()
    if feature == "music":
        credits = max(0, _env_int("MUSIC_DAILY_CREDITS", 3))
        window_h = _env_int("MUSIC_CREDIT_WINDOW_HOURS", 24)
        return {
            "feature": "music",
            "window_s": max(3600, min(DURATION * 30, window_h * 3600)),
            "credits": credits,
            "unit_cost": max(0, _env_int("MUSIC_CLIP_CREDITS", 1)),
        }
    if feature == "video":
        credits = max(0, _env_int("VIDEO_DAILY_CREDITS", 5))
        window_h = _env_int("VIDEO_CREDIT_WINDOW_HOURS", 24)
        return {
            "feature": "video",
            "window_s": max(3600, min(DURATION * 30, window_h * 3600)),
            "credits": credits,
            "unit_cost": max(0, _env_int("VIDEO_CLIP_CREDITS", 1)),
            "hd_cost": max(0, _env_int("VIDEO_HD_CREDITS", 2)),
            "hd_pixels": max(1, _env_int("VIDEO_HD_PIXELS", 832 * 480)),
            "max_seconds": max(1, _env_int("VIDEO_MAX_DURATION_SECONDS", 10)),
        }
    raise ValueError(f"unknown quota feature: {feature!r}")


def video_cost(seconds: float, width: int, height: int) -> int:
    """Credits for one scene clip — cost grows with the work it asks for."""
    cfg = config("video")
    cost = cfg["unit_cost"]
    if seconds > 5.0 or (width * height) > cfg["hd_pixels"]:
        cost = cfg["hd_cost"]
    return max(0, cost)


def video_max_seconds() -> int:
    return config("video")["max_seconds"]


def clamp_video_seconds(seconds: float) -> float:
    """Clamp one clip to the configured ceiling. Never raises."""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        value = 4.0
    if not math.isfinite(value):
        value = 4.0
    return max(1.0, min(float(video_max_seconds()), value))


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #

def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.conn = c
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS generation_ledger (
                user_key TEXT NOT NULL,
                feature TEXT NOT NULL,
                window_start REAL NOT NULL,
                credits_used INTEGER NOT NULL DEFAULT 0,
                updated REAL NOT NULL,
                PRIMARY KEY (user_key, feature)
            );
            CREATE TABLE IF NOT EXISTS generation_jobs (
                id TEXT PRIMARY KEY,
                user_key TEXT NOT NULL,
                feature TEXT NOT NULL,
                credits INTEGER NOT NULL,
                fingerprint TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL,            -- reserved | settled | released
                outcome TEXT NOT NULL DEFAULT '',
                created REAL NOT NULL,
                updated REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gen_jobs_fp
                ON generation_jobs (user_key, feature, fingerprint, created DESC);
            CREATE INDEX IF NOT EXISTS idx_gen_jobs_ledger
                ON generation_jobs (user_key, feature, created DESC);
            """
        )
    return c


def key_for(token_or_ip: str) -> str:
    """Opaque, stable per-caller key. Raw tokens and IPs are never stored."""
    return hashlib.sha256(("fenix-quota:" + str(token_or_ip or "anon")).encode()).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# Reading state
# --------------------------------------------------------------------------- #

def snapshot(feature: str, user_key: str) -> dict:
    """Remaining allowance, its window and the cooldown — server-side truth."""
    cfg = config(feature)
    now = time.time()
    used, start = 0.0, now
    try:
        with _lock:
            row = _conn().execute(
                "SELECT window_start, credits_used FROM generation_ledger"
                " WHERE user_key=? AND feature=?", (user_key, feature)).fetchone()
        if row is not None and now - row["window_start"] < cfg["window_s"]:
            used, start = float(row["credits_used"]), float(row["window_start"])
    except Exception:  # a metering table that cannot be read must not block use
        return _empty(cfg, 0, now, now)
    return _empty(cfg, used, start, now)


def _empty(cfg: dict, used: float, start: float, now: float) -> dict:
    limit = cfg["credits"]
    remaining = max(0, int(math.floor(limit - used)))
    elapsed = max(0.0, now - start)
    reset_at = start + cfg["window_s"]
    return {
        "feature": cfg["feature"],
        "limit": limit,
        "used": int(math.floor(used)),
        "remaining": remaining,
        "unit_cost": cfg["unit_cost"],
        "window_seconds": cfg["window_s"],
        "reset_at": reset_at,
        "reset_in": int(max(0, round(reset_at - now))),
        "progress": 0.0 if limit <= 0 else round(min(1.0, elapsed / cfg["window_s"]), 4),
    }


def _cooldown_left(c: sqlite3.Connection, user_key: str, feature: str,
                    fingerprint: str, now: float) -> int:
    """Seconds to wait before the same job may be submitted again.

    Only a job that ran the engine counts — one still in flight, or one that
    produced something. A job that failed and was released does not: the caller
    already saw the real reason and must be free to try again immediately,
    otherwise the cooldown would only hide the honest error behind a vague one.
    """
    window = cooldown_s()
    if window <= 0 or not fingerprint:
        return 0
    row = c.execute(
        "SELECT created FROM generation_jobs WHERE user_key=? AND feature=?"
        " AND fingerprint=? AND state IN ('reserved','settled')"
        " ORDER BY created DESC LIMIT 1",
        (user_key, feature, fingerprint)).fetchone()
    if row is None:
        return 0
    left = window - (now - float(row["created"]))
    return int(left) + 1 if left > 0 else 0


# --------------------------------------------------------------------------- #
# Reserving / settling
# --------------------------------------------------------------------------- #

def reserve(feature: str, user_key: str, credits: int = 0, fingerprint: str = "",
            note: str = "") -> dict:
    """Atomically take one job's worth of credits, about to be spent on inference.

    `credits` of 0 (or None) means the feature's default cost; pass a positive
    number when the caller knows the job is bigger than the default.

    Returns a dict. `granted` True means the inference may run; `id` must later
    be handed to settle() or release(). Nothing is written when not granted.
    """
    cfg = config(feature)
    now = time.time()
    if not enabled():
        return {"granted": True, "id": secrets.token_hex(8), "free": True,
                "snapshot": _empty(cfg, 0, now, now)}
    # 0 / None means "the default cost for this feature"; a caller that knows
    # the size of the job (a longer or larger clip) passes it explicitly.
    try:
        asked = int(credits or 0)
    except (TypeError, ValueError):
        asked = 0
    cost = cfg["unit_cost"] if asked <= 0 else asked

    with _lock:
        c = _conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            left = _cooldown_left(c, user_key, feature, fingerprint, now)
            if left:
                c.execute("COMMIT")
                return {"granted": False, "code": "COOLDOWN", "retry_after": left,
                        "snapshot": snapshot(feature, user_key)}

            row = c.execute(
                "SELECT window_start, credits_used FROM generation_ledger"
                " WHERE user_key=? AND feature=?", (user_key, feature)).fetchone()
            if row is None or now - float(row["window_start"]) >= cfg["window_s"]:
                start, used = now, 0
            else:
                start, used = float(row["window_start"]), int(row["credits_used"])

            if used + cost > cfg["credits"]:
                c.execute("COMMIT")
                return {"granted": False, "code": "QUOTA_EXCEEDED",
                        "snapshot": _empty(cfg, used, start, now)}

            job_id = secrets.token_hex(8)
            c.execute(
                "INSERT INTO generation_jobs"
                " (id, user_key, feature, credits, fingerprint, state, outcome, created, updated)"
                " VALUES (?,?,?,?,?,'reserved','',?,?)",
                (job_id, user_key, feature, cost, fingerprint[:200], now, now))
            c.execute(
                "INSERT INTO generation_ledger (user_key, feature, window_start, credits_used, updated)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(user_key, feature) DO UPDATE SET"
                "   window_start=excluded.window_start,"
                "   credits_used=excluded.credits_used, updated=excluded.updated",
                (user_key, feature, start, used + cost, now))
            c.execute("COMMIT")
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            # Metering must never be the reason a working product breaks.
            return {"granted": True, "id": secrets.token_hex(8), "unmetered": True,
                    "snapshot": _empty(cfg, 0, now, now)}
    return {"granted": True, "id": job_id, "snapshot": _empty(cfg, used + cost, start, now)}


def settle(job_id: str, ok: bool, refund: bool = False, outcome: str = "") -> dict:
    """Finish a job. `refund=True` gives the credit back (engine never ran)."""
    if not job_id:
        return {"ok": True, "noop": True}
    now = time.time()
    with _lock:
        c = _conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT user_key, feature, credits, state FROM generation_jobs"
                            " WHERE id=?", (job_id,)).fetchone()
            if row is None:
                c.execute("COMMIT")
                return {"ok": False, "reason": "unknown job"}
            if row["state"] != "reserved":
                c.execute("COMMIT")
                return {"ok": False, "reason": f"already {row['state']}"}
            state = "settled" if (ok and not refund) else (
                "released" if refund else "settled")
            c.execute("UPDATE generation_jobs SET state=?, outcome=?, updated=? WHERE id=?",
                      (state, str(outcome)[:200], now, job_id))
            if refund:
                # Clamped at zero so a released job can never mint credit.
                c.execute("UPDATE generation_ledger SET credits_used=MAX(0, credits_used-?), updated=?"
                          " WHERE user_key=? AND feature=?",
                          (int(row["credits"]), now, row["user_key"], row["feature"]))
            c.execute("COMMIT")
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            return {"ok": False, "reason": "settle failed"}
    return {"ok": True, "state": state}


def refund(job_id: str, outcome: str = "") -> dict:
    return settle(job_id, ok=False, refund=True, outcome=outcome)


def report(user_key: str) -> dict:
    """Both features at once — what the UI polls."""
    out = {f: snapshot(f, user_key) for f in FEATURES}
    return {
        "features": out,
        "enabled": enabled(),
        "cooldown_seconds": cooldown_s(),
        "server_time": time.time(),
    }


# --------------------------------------------------------------------------- #
# Admin / test helpers
# --------------------------------------------------------------------------- #

def reset(user_key: str, feature: str = "") -> None:
    """Clear metering for one caller. Used by the test-suite and by admins."""
    with _lock:
        c = _conn()
        if feature:
            c.execute("DELETE FROM generation_ledger WHERE user_key=? AND feature=?",
                      (user_key, feature))
            c.execute("DELETE FROM generation_jobs WHERE user_key=? AND feature=?",
                      (user_key, feature))
        else:
            c.execute("DELETE FROM generation_ledger WHERE user_key=?", (user_key,))
            c.execute("DELETE FROM generation_jobs WHERE user_key=?", (user_key,))
