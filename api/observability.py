"""Small privacy-safe observability layer for Fenix tool and model calls."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid

LOGGER = logging.getLogger("fenix.observability")


def _enabled() -> bool:
    return os.environ.get("FENIX_OBSERVABILITY", "1").strip().lower() not in ("0", "off", "false", "none")


def event(kind: str, **fields: object) -> None:
    if not _enabled():
        return
    safe = {k: v for k, v in fields.items() if k not in {"api_key", "key", "token", "authorization", "content", "text"}}
    LOGGER.info(json.dumps({"event": kind, "id": uuid.uuid4().hex[:12], "ts": time.time(), **safe}, default=str))


def tool_event(tool: str, status: str, started: float, **fields: object) -> None:
    event("tool_call", tool=tool, status=status, latencyMs=round((time.perf_counter() - started) * 1000, 2), **fields)
