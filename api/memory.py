"""
Fenix Memory — structured, user-controlled memory store.

Categories (A–F from the Fenix spec):
  preferences  — user preferences
  projects     — what the user is working on
  goals        — long-term goals
  style        — working style
  facts        — important facts explicitly saved by the user
  context      — temporary conversation context

Storage: one JSON file per user under .data/memory/ (gitignored).
Nothing is stored automatically except temporary context; every long-term
entry is either user-saved or explicitly confirmed ("remember this?").
"""
import os
import re
import secrets
import threading
import time

from store import _read, _write, DATA_DIR

CATEGORIES = ("preferences", "projects", "goals", "style", "facts", "context")
MAX_ENTRIES = 400
MAX_TEXT = 2000

_lock = threading.Lock()


def _memory_path(token: str) -> str:
    from store import _user_key  # local import to avoid import cycles

    email = _user_key(token)
    safe = re.sub(r"[^a-z0-9._-]", "_", email.lower())
    return os.path.join(DATA_DIR, "memory", safe + ".json")


def _load(token: str) -> dict:
    return _read(_memory_path(token), {"entries": [], "counter": 0})


def _save(token: str, data: dict) -> None:
    _write(_memory_path(token), data)


def list_memory(token: str, category: str | None = None) -> list[dict]:
    """All entries (optionally one category), newest first."""
    data = _load(token)
    entries = data.get("entries", [])
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return list(reversed(entries))


def add_entry(token: str, category: str, text: str, source: str = "user") -> dict:
    """Add one memory entry. source: 'user' (explicit) or 'assistant-proposed'."""
    category = category if category in CATEGORIES else "facts"
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("Memory text is empty")
    with _lock:
        data = _load(token)
        data["counter"] = data.get("counter", 0) + 1
        entry = {
            "id": "m" + secrets.token_urlsafe(6),
            "category": category,
            "text": text,
            "source": source if source in ("user", "assistant-proposed") else "user",
            "created": time.time(),
            "n": data["counter"],
        }
        entries = data.setdefault("entries", [])
        entries.append(entry)
        # Data minimization: cap total entries; drop oldest context first.
        if len(entries) > MAX_ENTRIES:
            entries.sort(key=lambda e: (e.get("category") != "context", e.get("created", 0)))
            del entries[0 : len(entries) - MAX_ENTRIES]
        _save(token, data)
    return entry


def update_entry(token: str, entry_id: str, text: str, category: str | None = None) -> bool:
    with _lock:
        data = _load(token)
        for e in data.get("entries", []):
            if e["id"] == entry_id:
                if text is not None:
                    e["text"] = text.strip()[:MAX_TEXT]
                if category in CATEGORIES:
                    e["category"] = category
                e["edited"] = time.time()
                _save(token, data)
                return True
    return False


def delete_entry(token: str, entry_id: str) -> bool:
    with _lock:
        data = _load(token)
        before = len(data.get("entries", []))
        data["entries"] = [e for e in data.get("entries", []) if e["id"] != entry_id]
        if len(data["entries"]) != before:
            _save(token, data)
            return True
    return False


def clear_category(token: str, category: str | None = None) -> int:
    """Clear one category or everything. Returns number of deleted entries."""
    with _lock:
        data = _load(token)
        entries = data.get("entries", [])
        if category in CATEGORIES:
            kept = [e for e in entries if e.get("category") != category]
        else:
            kept = []
        deleted = len(entries) - len(kept)
        data["entries"] = kept
        _save(token, data)
        return deleted


def export_memory(token: str) -> dict:
    """Full export for the user (view/download)."""
    data = _load(token)
    return {
        "exported": time.time(),
        "categories": CATEGORIES,
        "entries": list(reversed(data.get("entries", []))),
    }


def memory_block(token: str | None, max_chars: int = 3000) -> str:
    """Render long-term memory for the system prompt (never 'context' category).
    Empty string when there is nothing useful."""
    if not token:
        return ""
    entries = [e for e in _load(token).get("entries", []) if e.get("category") != "context"]
    if not entries:
        return ""
    label = {
        "preferences": "Preferences", "projects": "Projects", "goals": "Goals",
        "style": "Working style", "facts": "Facts the user saved",
    }
    lines = []
    total = 0
    for e in reversed(entries):  # newest first, keep the freshest
        line = f"- [{label.get(e['category'], e['category'])}] {e['text']}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return ""
    return "\n# What you remember about this user\n(Only mention these when relevant; do not recite them.)\n" + "\n".join(reversed(lines))
