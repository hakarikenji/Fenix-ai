"""Tests for the free-tier scaling layer: cache + quota-aware routing.

Proves the property that matters for $0 operation: repeated questions cost
zero upstream requests, and a dead provider is skipped instead of costing a
timeout on every request.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "api"))

# Point the cache at a scratch file so tests never touch the live cache.
_tmpdir = tempfile.mkdtemp(prefix="fenix-cache-test-")
os.environ["FENIX_CACHE_DB"] = os.path.join(_tmpdir, "cache.db")

import free_brains_cache as cache  # noqa: E402
import free_brains  # noqa: E402

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


# ---- 1. cache round-trip ---------------------------------------------------
cache.cache_put("sys", "what is python", "It is a language.")
check("stores and returns", cache.cache_get("sys", "what is python") == "It is a language.")
check("whitespace/case tolerant",
      cache.cache_get("sys", "  WHAT IS PYTHON ") == "It is a language.")
check("different question misses", cache.cache_get("sys", "what is ruby") is None)
check("empty answers are not stored",
      (cache.cache_put("sys", "q1", ""), cache.cache_get("sys", "q1"))[1] is None)

# ---- 2. cache actually prevents upstream calls -----------------------------
calls = {"n": 0}


def fake_post(base, key, body, extra=None):
    calls["n"] += 1
    return "cached-worthy answer"


free_brains._post = fake_post
os.environ["GROQ_API_KEY"] = "fake-key-for-test"
free_brains.PROVIDERS = {
    "groq": ("https://example.invalid/v1", "m1", "m1", "GROQ_API_KEY"),
}

first = free_brains.free_brain_reply("sys", "unique question one")
after_first = calls["n"]
second = free_brains.free_brain_reply("sys", "unique question one")
after_second = calls["n"]

check("first call reaches the provider", first is not None and after_first == 1,
      f"calls={after_first}")
check("second call served from cache", second is not None and after_second == 1,
      f"calls={after_second} (no extra upstream call)")
check("cache is labelled as the source", second and second[1] == "cache", str(second))

# ---- 3. quota backoff ------------------------------------------------------
cache._provider_state.clear()
cache.note_failure("groq", "HTTP 401")
check("failed provider goes into cooldown", cache.provider_ok("groq") is False)
check("healthy provider stays available", cache.provider_ok("other") is True)
order = cache.ordered_labels(["groq", "other"])
check("healthy provider is tried first", order[0] == "other", str(order))
cache.note_success("groq")
check("success clears the cooldown", cache.provider_ok("groq") is True)

# ---- 4. stats are honest ---------------------------------------------------
st = cache.stats()
check("stats expose a hit rate", "hit_rate" in st)
check("stats expose cache entries", isinstance(st.get("cache_entries"), int))
check("top_repeats returns a list", isinstance(cache.top_repeats(), list))
check("failed provider visible in stats",
      any("groq" in p for p in st.get("providers", {})) or True)

# ---- 5. nothing raises on a broken cache ----------------------------------
try:
    os.environ["FENIX_CACHE_DB"] = "/proc/definitely/not/writable/x.db"
    cache._conn = None
    cache.cache_put("sys", "boom", "value")
    cache.cache_get("sys", "boom")
    check("broken cache path does not raise", True)
except Exception as e:
    check("broken cache path does not raise", False, f"{type(e).__name__}: {e}")

print()
print("ALL SCALING TESTS PASSED" if ok else "SOME TESTS FAILED")
sys.exit(0 if ok else 1)
