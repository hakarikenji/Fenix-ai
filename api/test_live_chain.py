"""Live end-to-end test of the real chain with both real keys present.

Verifies: a real Arabic answer arrives, which provider answered, the answer
survives identity sanitising, and the cache serves a repeat at zero upstream
cost.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "api"))

import free_brains  # noqa: E402
import identity_guard  # noqa: E402

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


SYSTEM = ("You are Fenix Core LoRA, the primary AI identity built by Hakari. "
          "Answer in the user's language. Be concise.")

free_brains.verify(force=True)
print("verified_count:", free_brains.verified_count())
print("providers      :", free_brains.verified_detail())
print()

res = free_brains.free_brain_reply(SYSTEM, "بجملة وحدة: ما هي عاصمة السعودية؟")
check("Arabic answer arrives", res is not None and bool(res[0].strip()), str(res)[:90])

if res:
    text, label = res
    print("   provider:", label)
    print("   answer  :", text.strip()[:160])
    arabic = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    check("answer is Arabic", arabic > 8, f"arabic_chars={arabic}")
    clean = identity_guard.sanitize_reply(text)
    check("survives identity guard", bool(clean.strip()))
    check("guard kept the Arabic", sum(1 for c in clean if "\u0600" <= c <= "\u06FF") > 8)

    # second call must come from cache
    hits_before = free_brains._cache.stats()["hits"]
    again = free_brains.free_brain_reply(SYSTEM, "بجملة وحدة: ما هي عاصمة السعودية؟")
    hits_after = free_brains._cache.stats()["hits"]
    check("repeat served from cache",
          again is not None and hits_after > hits_before,
          f"hits {hits_before} -> {hits_after}")
    check("cache is labelled as source", again and again[1] == "cache", str(again[1]) if again else "")

print()
print("cache:", {k: v for k, v in free_brains._cache.stats().items() if k != "providers"})
print("ALL LIVE TESTS PASSED" if ok else "SOME LIVE TESTS FAILED")
sys.exit(0 if ok else 1)
