"""Fenix semantic memory retrieval — pick the memories relevant to the question.

Why: injecting the whole memory block wastes context and degrades long-term
use. This module embeds every memory entry into a fixed-size vector using a
deterministic, dependency-free hashing scheme (character n-grams -> buckets),
stores vectors in SQLite, and retrieves the top-k entries by cosine similarity
for the current message.

This is a pragmatic local approach: it works offline, costs nothing, and is
swappable for a real embedding model later (same interface, one provider).
"""
from __future__ import annotations

import re

import db

DIM = 256          # vector size
NGRAM = 3          # character n-gram size
TOP_K = 12
MIN_SCORE = 0.18   # below this, the memory is not relevant enough to inject
TOP_MARGIN = 0.55  # keep entries scoring at least this fraction of the best

_word_re = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def _embed(text: str) -> list[float]:
    """Hashed features: full-word tokens (strong) + char n-grams (fuzzy)."""
    v = [0.0] * DIM
    words = [w.lower() for w in _word_re.findall((text or ""))]
    t = " ".join(words)
    if not t:
        return v

    def _add(feature: str, weight: float) -> None:
        h = 0
        for ch in feature:
            h = (h * 131 + ord(ch)) & 0xFFFFFFFF
        idx = h % DIM
        sign = 1.0 if (h >> 16) & 1 else -1.0
        v[idx] += weight * sign

    for w in set(words):        # whole words carry the most signal
        _add("w:" + w, 2.0)
    for i in range(max(1, len(t) - NGRAM + 1)):
        _add("g:" + t[i:i + NGRAM], 1.0)
    norm = sum(x * x for x in v) ** 0.5
    if norm > 0:
        v = [x / norm for x in v]
    return v


def index_memory(token: str, entry_id: str, text: str) -> None:
    """(Re)embed one memory entry. Cheap enough to call on every write."""
    vec = _embed(text)
    if any(vec):
        db.store_embedding(token, entry_id, vec)


def reindex_all(token: str, entries: list[dict]) -> int:
    """Rebuild vectors for a user's whole memory (called after edits/import)."""
    n = 0
    for e in entries:
        if e.get("category") == "context":
            continue
        index_memory(token, e.get("id", ""), e.get("text", ""))
        n += 1
    return n


def relevant_block(token: str, query: str, entries: list[dict], max_chars: int = 3000) -> str:
    """Render only the memory entries relevant to this query.

    Falls back to the classic newest-first block when embeddings are missing
    (e.g. first run) so behavior never degrades.
    """
    by_id = {e.get("id"): e for e in entries if e.get("category") != "context"}
    if not by_id or not (query or "").strip():
        return ""
    qv = _embed(query)
    scored: list[tuple[float, str, dict]] = []
    vecs = db.all_embeddings(token)
    have_vectors = False
    for eid, e in by_id.items():
        vec = vecs.get(eid)
        if not vec:
            continue
        have_vectors = True
        s = db.cosine(qv, vec)
        if s >= MIN_SCORE:
            scored.append((s, eid, e))
    if not have_vectors:
        return ""            # caller falls back to the full memory block
    scored.sort(key=lambda x: -x[0])
    if scored:
        best = scored[0][0]
        scored = [s for s in scored if s[0] >= best * TOP_MARGIN]
    label = {
        "preferences": "Preferences", "projects": "Projects", "goals": "Goals",
        "style": "Working style", "facts": "Facts the user saved",
    }
    lines, total = [], 0
    for _, _, e in scored[:TOP_K]:
        line = f"- [{label.get(e['category'], e['category'])}] {e['text']}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return ""
    return ("\n# What you remember about this user (relevant to this message)\n"
            "(Only mention these when relevant; do not recite them.)\n"
            + "\n".join(lines))
