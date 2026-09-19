"""
Phoenix Evolution — evidence-based learning profile about how Phoenix should
work with each user. Strictly separated from memory:

  Memory   = information ABOUT the user's world (facts, projects, goals).
  Evolution= how Phoenix adapts its BEHAVIOR (communication, work style).

Rules (from the Phoenix spec):
- Never invent traits: an insight needs >= MIN_EVIDENCE observations.
- Everything is inspectable, editable and deletable by the user.
- Evolution can be disabled entirely (enabled: false) — then nothing is
  applied and nothing new is recorded.
"""
import os
import re
import secrets
import threading
import time

from store import _read, _write, DATA_DIR

MIN_EVIDENCE = 3          # observations required before an insight becomes active
MAX_INSIGHTS = 40
MAX_LOG = 60

DIMENSIONS = ("communication", "work_style", "project_interaction")

_lock = threading.Lock()


def _evo_path(token: str) -> str:
    from store import _user_key

    email = _user_key(token)
    safe = re.sub(r"[^a-z0-9._-]", "_", email.lower())
    return os.path.join(DATA_DIR, "evolution", safe + ".json")


def _load(token: str) -> dict:
    return _read(_evo_path(token), {"enabled": True, "insights": [], "log": [], "counter": 0})


def _save(token: str, data: dict) -> None:
    _write(_evo_path(token), data)


def is_enabled(token: str) -> bool:
    return bool(_load(token).get("enabled", True))


def set_enabled(token: str, enabled: bool) -> dict:
    data = _load(token)
    data["enabled"] = bool(enabled)
    _save(token, data)
    return {"enabled": data["enabled"]}


def profile(token: str) -> dict:
    """Full evolution profile + log for the UI."""
    data = _load(token)
    return {
        "enabled": data.get("enabled", True),
        "insights": list(reversed(data.get("insights", []))),
        "log": list(reversed(data.get("log", []))),
        "min_evidence": MIN_EVIDENCE,
    }


def observe(token: str, dimension: str, observation: str, change: str, reason: str) -> dict | None:
    """Record one observation. Promotes to an active insight once evidence
    reaches MIN_EVIDENCE. Returns the log entry (or None if disabled)."""
    dimension = dimension if dimension in DIMENSIONS else "communication"
    observation = (observation or "").strip()[:500]
    change = (change or "").strip()[:500]
    reason = (reason or "").strip()[:500]
    if not observation:
        return None
    with _lock:
        data = _load(token)
        if not data.get("enabled", True):
            return None
        insights = data.setdefault("insights", [])
        entry = None
        for ins in insights:
            if ins["dimension"] == dimension and ins["observation"].lower() == observation.lower():
                ins["evidence"] = ins.get("evidence", 0) + 1
                ins["last_seen"] = time.time()
                if ins.get("evidence", 0) >= MIN_EVIDENCE and not ins.get("active"):
                    ins["active"] = True
                    ins["activated"] = time.time()
                entry = ins
                break
        if entry is None:
            entry = {
                "id": "e" + secrets.token_urlsafe(6),
                "dimension": dimension,
                "observation": observation,
                "change": change,
                "evidence": 1,
                "active": False,  # needs MIN_EVIDENCE observations first
                "created": time.time(),
                "last_seen": time.time(),
            }
            insights.append(entry)
        data["counter"] = data.get("counter", 0) + 1
        log_entry = {
            "id": "l" + secrets.token_urlsafe(6),
            "n": data["counter"],
            "date": time.strftime("%Y-%m-%d"),
            "dimension": dimension,
            "observation": observation,
            "change": change or "(observed — no behavior change yet)",
            "reason": reason or "Observed pattern in recent conversations.",
            "evidence": entry.get("evidence", 1),
            "activated": entry.get("active", False),
            "created": time.time(),
        }
        data.setdefault("log", []).append(log_entry)
        del data["log"][:-MAX_LOG]
        del insights[:-MAX_INSIGHTS]
        _save(token, data)
    return log_entry


def update_insight(token: str, insight_id: str, change: str | None = None, observation: str | None = None) -> bool:
    """User correction of an insight's wording/behavior."""
    with _lock:
        data = _load(token)
        for ins in data.get("insights", []):
            if ins["id"] == insight_id:
                if observation is not None:
                    ins["observation"] = observation.strip()[:500]
                if change is not None:
                    ins["change"] = change.strip()[:500]
                ins["edited"] = time.time()
                _save(token, data)
                return True
    return False


def delete_insight(token: str, insight_id: str) -> bool:
    with _lock:
        data = _load(token)
        before = len(data.get("insights", []))
        data["insights"] = [i for i in data.get("insights", []) if i["id"] != insight_id]
        if len(data["insights"]) != before:
            _save(token, data)
            return True
    return False


def clear_all(token: str) -> int:
    with _lock:
        data = _load(token)
        n = len(data.get("insights", []))
        data["insights"] = []
        data["log"] = []
        _save(token, data)
        return n


def evolution_block(token: str | None, max_chars: int = 1600) -> str:
    """Active insights rendered for the system prompt ('' when none/disabled)."""
    if not token:
        return ""
    data = _load(token)
    if not data.get("enabled", True):
        return ""
    active = [i for i in data.get("insights", []) if i.get("active")]
    if not active:
        return ""
    lines, total = [], 0
    for ins in active:
        line = f"- [{ins['dimension']}] {ins['change'] or ins['observation']}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return ""
    return (
        "\n# How you work with this user (learned from repeated interactions)\n"
        + "\n".join(lines)
        + "\nIf asked why you behave differently, explain these patterns honestly — never reveal hidden reasoning."
    )
