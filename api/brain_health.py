"""Fenix brain health — periodic real probe of the Fenix Core LoRA endpoint.

The honesty rule: a configured URL is not a live brain until it has answered a
real request. This module probes the brain (cheap GET health, then a tiny real
POST) on a background schedule and stores the result in SQLite, so /api/brains
always reflects reality without making every chat wait on a probe.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

import db

PROBE_INTERVAL_S = 300          # re-probe every 5 minutes
STALE_AFTER_S = 900             # older than 15 min → treat as unknown

_lock = threading.Lock()


def _urls() -> list[str]:
    urls: list[str] = []
    custom = os.environ.get("CUSTOM_LLM_BASE_URL", "").rstrip("/")
    if custom:
        urls.append(custom)
    for env in ("CORE_HF_URL",):
        u = os.environ.get(env, "").strip().rstrip("/")
        if u:
            urls.append(u)
    return urls


def _probe_once(url: str, timeout: float = 20.0) -> tuple[str, str]:
    """Returns (state, detail). state in live | down."""
    try:
        req = urllib.request.Request(url + "/chat/completions", data=json.dumps({
            "model": os.environ.get("CUSTOM_LLM_MODEL", "fenix-core"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        }).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8", "ignore"))
        text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        return ("live", "ok") if text else ("down", "empty reply")
    except Exception as e:
        return "down", type(e).__name__


def probe() -> dict:
    urls = _urls()
    if not urls:
        return {"state": "unconfigured", "checked_at": 0, "detail": ""}
    for url in urls:
        state, detail = _probe_once(url)
        if state == "live":
            db.set_brain_health("live", url.split("//")[-1][:60])
            return {"state": "live", "checked_at": time.time(), "detail": ""}
    db.set_brain_health("down", detail)
    return {"state": "down", "checked_at": time.time(), "detail": detail}


def status() -> dict:
    """Cached status; probes in the background when stale. Never blocks long."""
    stored = db.get_brain_health()
    fresh = stored and (time.time() - stored["checked_at"]) < STALE_AFTER_S
    if not _urls():
        return {"state": "unconfigured", "checked_at": 0}
    if fresh:
        return {"state": stored["state"], "checked_at": stored["checked_at"]}
    if _lock.acquire(blocking=False):
        def run():
            try:
                probe()
            finally:
                _lock.release()
        threading.Thread(target=run, daemon=True).start()
    # First read may still see stale data; that is the honest cached truth.
    return {"state": (stored or {}).get("state", "unknown"),
            "checked_at": (stored or {}).get("checked_at", 0)}


def start_background() -> None:
    def loop():
        time.sleep(5)
        while True:
            try:
                if _urls():
                    probe()
            except Exception:
                pass
            time.sleep(PROBE_INTERVAL_S)
    threading.Thread(target=loop, daemon=True).start()
