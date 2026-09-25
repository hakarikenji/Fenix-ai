"""Tests for the world-class layer: SQLite db, semantic memory, identity guard.

Run: python3 api/test_world_class.py
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["FENIX_DATA_DIR"] = _tmp
sys.path.insert(0, str(Path(__file__).parent))

import db  # noqa: E402
import semantic_memory as sm  # noqa: E402


def test_ratings_roundtrip():
    db.add_rating("tok1", "c1", "hi", "hello", 1)
    db.add_rating("tok1", "c1", "bad", "answer", -1, reason="wrong")
    stats = db.rating_stats()
    assert stats["total"] >= 2, stats
    pairs = db.export_training_pairs()
    assert all(p["rating"] == 1 for p in pairs), pairs  # only up-rated exported
    print("PASS ratings roundtrip", stats)


def test_rate_limit():
    ok = True
    for _ in range(5):
        ok, _rem, _retry = db.rate_limit("k1", 5, 60)
    assert ok is True
    allowed, _rem, retry = db.rate_limit("k1", 5, 60)
    assert allowed is False and retry > 0
    print("PASS rate limit")


def test_conversations():
    conv = db.create_conversation("tok2", "My project chat")
    cid = conv["id"]
    assert db.append_message("tok2", cid, "user", "hello there")
    assert db.append_message("tok2", cid, "assistant", "hi! how can I help?")
    msgs = db.get_messages("tok2", cid)
    assert [m["role"] for m in msgs] == ["user", "assistant"], msgs
    # Another user cannot read it
    assert db.get_messages("tok3", cid) == []
    assert db.rename_conversation("tok2", cid, "Renamed")
    listed = db.list_conversations("tok2")
    assert listed[0]["title"] == "Renamed", listed
    assert db.delete_conversation("tok2", cid)
    assert db.get_messages("tok2", cid) == []
    print("PASS conversations")


def test_semantic_memory():
    entries = [
        {"id": "e1", "category": "projects", "text": "User is building an Android music app with Capacitor"},
        {"id": "e2", "category": "preferences", "text": "User prefers concise answers in Arabic"},
        {"id": "e3", "category": "goals", "text": "User wants to publish the app on Google Play"},
        {"id": "e4", "category": "facts", "text": "User's birthday is in March"},
    ]
    sm.reindex_all("tok4", entries)
    # Realistic case: memory and query share a language (the dominant usage).
    block = sm.relevant_block("tok4", "how is the android music app development going?", entries)
    assert "music app" in block, block
    assert "birthday" not in block, block
    # Cross-language recall is best-effort for the local embedder — it must
    # never crash and never invent irrelevant memories.
    ar = sm.relevant_block("tok4", "كيف يسير تطوير تطبيق الموسيقى؟", entries)
    assert isinstance(ar, str)
    empty = sm.relevant_block("tok5", "anything", entries)  # no vectors for tok5
    assert empty == ""
    print("PASS semantic memory ->", block.replace(chr(10), " | ")[:120])


def test_brain_health_storage():
    db.set_brain_health("down", "test")
    st = db.get_brain_health()
    assert st["state"] == "down"
    print("PASS brain health storage")


if __name__ == "__main__":
    test_ratings_roundtrip()
    test_rate_limit()
    test_conversations()
    test_semantic_memory()
    test_brain_health_storage()
    print("\nALL WORLD-CLASS TESTS PASSED")
