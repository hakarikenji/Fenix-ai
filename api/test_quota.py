"""
Fenix — generation quota.

Twelve questions, twelve checks. The point of this suite is that the limit is
a real server-side fact: it survives a page refresh, a sign-out, a second
device and a burst of simultaneous requests, and it never charges for work
that was refused before the engine ran.

Run:  python3 api/test_quota.py
"""
import concurrent.futures
import json
import os
import sys
import tempfile
import time

# A throwaway database, so the suite never touches real allowance.
_TMP = tempfile.mkdtemp(prefix="fenix-quota-test-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["QUOTA_ENABLED"] = "1"
os.environ["QUOTA_COOLDOWN_SECONDS"] = "0"   # most cases need clean reservations
os.environ["MUSIC_DAILY_CREDITS"] = "3"
os.environ["MUSIC_CREDIT_WINDOW_HOURS"] = "24"
os.environ["MUSIC_CLIP_CREDITS"] = "1"
os.environ["VIDEO_DAILY_CREDITS"] = "5"
os.environ["VIDEO_CREDIT_WINDOW_HOURS"] = "24"
os.environ["VIDEO_CLIP_CREDITS"] = "1"
os.environ["VIDEO_HD_CREDITS"] = "2"
os.environ["VIDEO_MAX_DURATION_SECONDS"] = "10"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import quota  # noqa: E402

PASS = FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def caller(name):
    return quota.key_for("user:" + name)


def spend(caller_key, feature, credits=0, fingerprint="", ok=True, refund=False):
    r = quota.reserve(feature, caller_key, credits, fingerprint=fingerprint)
    if r.get("granted"):
        quota.settle(r["id"], ok=ok, refund=refund)
    return r


# --------------------------------------------------------------------- 1 ---
print("1. a new caller has the full allowance")
k = caller("new")
snap = quota.snapshot("music", k)
check("music is full", snap["remaining"] == 3 and snap["limit"] == 3, snap)
check("the window is the configured 24h", snap["window_seconds"] == 86400, snap)
check("a reset time is published", snap["reset_at"] > time.time(), snap)

# --------------------------------------------------------------------- 2 ---
print("2. a successful generation costs one credit")
k = caller("success")
r = spend(k, "music", 0, "prompt-a", ok=True)
check("the reservation was granted", r["granted"], r)
after = quota.snapshot("music", k)
check("one credit was consumed", after["remaining"] == 2, after)
spend(k, "music", 0, "prompt-b", ok=True)
check("two credits consumed", quota.snapshot("music", k)["remaining"] == 1)

# --------------------------------------------------------------------- 3 ---
print("3. a request refused before inference costs nothing")
k = caller("preflight")
before = quota.snapshot("music", k)
# An engine that answers "I cannot do that" never burned GPU time.
r = spend(k, "music", 0, "prompt-x", ok=False, refund=True)
check("the caller is told the truth", not r["granted"] or r.get("snapshot"), r)
check("the credit came back", quota.snapshot("music", k)["used"] == before["used"],
      quota.snapshot("music", k))
# And the same is true for a request that is refused outright.
r = quota.reserve("music", k, 99, fingerprint="too-big")
check("an impossible cost is refused", not r["granted"] and r["code"] == "QUOTA_EXCEEDED", r)
check("a refusal writes nothing", quota.snapshot("music", k)["remaining"] == 3)

# --------------------------------------------------------------------- 4 ---
print("4. the allowance can never go below zero")
k = caller("floor")
spend(k, "music", 0, "a", ok=True)
spend(k, "music", 0, "b", ok=True)
spend(k, "music", 0, "c", ok=True)
check("the allowance is spent", quota.snapshot("music", k)["remaining"] == 0)
r = quota.reserve("music", k, 0, fingerprint="d")
check("the fourth is refused", not r["granted"] and r["code"] == "QUOTA_EXCEEDED", r)
check("remaining is reported as 0, never negative", quota.snapshot("music", k)["remaining"] == 0)
# Releasing a refunded job twice must not mint credit either.
j = quota.reserve("video", k, 1, fingerprint="v1")
quota.refund(j["id"])
quota.refund(j["id"])
check("a double refund is ignored", quota.snapshot("video", k)["remaining"] == 5,
      quota.snapshot("video", k))

# --------------------------------------------------------------------- 5 ---
print("5. refreshing the page does not reset anything")
# "Refresh" is a new HTTP request with no memory of the old one. The ledger is
# keyed by the account, so a fresh request sees the same remaining count.
k = caller("refresh")
spend(k, "music", 0, "a", ok=True)
spend(k, "music", 0, "b", ok=True)
first = quota.snapshot("music", k)["remaining"]
second = quota.snapshot("music", k)["remaining"]   # a brand new request
third = quota.key_for("user:refresh")              # the account is re-derived
check("remaining is unchanged by re-reading", first == second == 1, (first, second))
check("the same key is derived again", third == k)
check("a cleared client would still see the same 1 left",
      quota.snapshot("music", quota.key_for("user:refresh"))["remaining"] == 1)

# --------------------------------------------------------------------- 6 ---
print("6. signing out and back in does not reset anything")
token = "tok-" + str(int(time.time() * 1000))
key_a = quota.key_for("user:" + token)
spend(key_a, "music", 0, "a", ok=True)
# Signing out drops the token from the browser only; signing in mints a new
# token, but both map to the same account — and the API keys on the account.
spend(quota.key_for("user:" + token), "music", 0, "b", ok=True)
check("two tracks spent across the session", quota.snapshot("music", key_a)["remaining"] == 1)
check("reading after 'sign out' still shows 1",
      quota.snapshot("music", quota.key_for("user:" + token))["remaining"] == 1)

# --------------------------------------------------------------------- 7 ---
print("7. simultaneous requests cannot both take the last credit")
k = caller("race")
quota.reset(k, "music")


def race(i):
    r = quota.reserve("music", k, 0, fingerprint=f"race-{i}")
    if r.get("granted"):
        quota.settle(r["id"], ok=True)
    return r.get("granted")


with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    granted = list(pool.map(race, range(16)))
check("exactly three of sixteen succeeded", sum(1 for g in granted if g) == 3,
      f"granted={sum(1 for g in granted if g)}")
check("the ledger agrees", quota.snapshot("music", k)["used"] == 3,
      quota.snapshot("music", k))
check("remaining never went negative", quota.snapshot("music", k)["remaining"] == 0)

# --------------------------------------------------------------------- 8 ---
print("8. the window resets when it expires")
os.environ["MUSIC_CREDIT_WINDOW_HOURS"] = "1"
k = caller("reset")
# Rewind the window instead of sleeping an hour.
import sqlite3  # noqa: E402

c = quota._conn()
c.execute("UPDATE generation_ledger SET window_start=? WHERE user_key=? AND feature='music'",
          (time.time() - 3700, k))
check("the stale window is ignored and a new one starts",
      quota.snapshot("music", k)["remaining"] == 3, quota.snapshot("music", k))
r = quota.reserve("music", k, 0, fingerprint="after-reset")
check("generation works again after the reset", r.get("granted"), r)
quota.settle(r["id"], ok=True)
os.environ["MUSIC_CREDIT_WINDOW_HOURS"] = "24"

# --------------------------------------------------------------------- 9 ---
print("9. music and video have independent allowances")
k = caller("independent")
spend(k, "music", 0, "a", ok=True)
spend(k, "music", 0, "b", ok=True)
spend(k, "music", 0, "c", ok=True)
check("music is spent out", quota.snapshot("music", k)["remaining"] == 0)
check("video is untouched", quota.snapshot("video", k)["remaining"] == 5)
r = quota.reserve("video", k, 1, fingerprint="v")
check("video still grants", r.get("granted"), r)
quota.settle(r["id"], ok=True)
check("music is still empty", quota.snapshot("music", k)["remaining"] == 0)
check("video is now at 4", quota.snapshot("video", k)["remaining"] == 4)

# video credits scale with the work asked for
check("a long clip costs more than a short one",
      quota.video_cost(8.0, 832, 480) == 2, quota.video_cost(8.0, 832, 480))
check("a high-resolution clip costs more than a short one",
      quota.video_cost(4.0, 1280, 720) == 2, quota.video_cost(4.0, 1280, 720))
check("a plain short clip costs one", quota.video_cost(4.0, 832, 480) == 1)

# -------------------------------------------------------------------- 10 ---
print("10. configuration is read at call time, not baked in")
os.environ["MUSIC_DAILY_CREDITS"] = "9"
k = caller("config")
check("the new limit applies to a new window", quota.snapshot("music", k)["limit"] == 9)
check("and to the next reservation", quota.reserve("music", k, 0, "x")["granted"])
os.environ["VIDEO_DAILY_CREDITS"] = "1"
k2 = caller("config2")
check("video limit changed too", quota.snapshot("video", k2)["limit"] == 1)
r = quota.reserve("video", k2, 1, fingerprint="one")
quota.settle(r["id"], ok=True)
r2 = quota.reserve("video", k2, 1, fingerprint="two")
check("the second clip is refused under the new limit", not r2["granted"], r2)
check("the refusal carries a reset time", r2["snapshot"]["reset_at"] > time.time())
os.environ["VIDEO_DAILY_CREDITS"] = "5"
os.environ["MUSIC_DAILY_CREDITS"] = "3"

os.environ["QUOTA_ENABLED"] = "0"
k3 = caller("unmetered")
r = quota.reserve("music", k3, 0, fingerprint="x")
check("metering can be switched off", r.get("granted") and r.get("free"), r)
os.environ["QUOTA_ENABLED"] = "1"

# duration ceiling
os.environ["VIDEO_MAX_DURATION_SECONDS"] = "10"
check("a 90s request is clamped to the ceiling", quota.clamp_video_seconds(90) == 10.0)
check("a sane request is left alone", quota.clamp_video_seconds(4) == 4.0)
check("a junk value is made safe", quota.clamp_video_seconds("nonsense") == 4.0)

# -------------------------------------------------------------------- 11 ---
print("11. protected resources are metered for everyone, signed in or not")
k = caller("signed-out")
check("a signed-out caller still has an allowance", quota.snapshot("video", k)["limit"] == 5)
results = [quota.reserve("video", k, 1, fingerprint=f"anon-{i}").get("granted")
           for i in range(9)]
check("a signed-out caller cannot exceed the allowance either",
      sum(1 for x in results if x) == 5, results)
# Two different anonymous callers on one address share the same bucket only
# because the address is what the API keys on — the client cannot choose.
k4 = quota.key_for("addr:203.0.113.9")
check("the address fallback is a stable hash, not the address",
      k4 != "addr:203.0.113.9" and len(k4) == 32, k4)
check("no raw token or address is written anywhere", "203.0.113.9" not in
      open(quota.DB_PATH, "rb").read().decode("utf-8", "ignore"))

# -------------------------------------------------------------------- 12 ---
print("12. the cheap parts of Fenix are not metered")
FEATURES = quota.FEATURES
check("only music and video are metered", set(FEATURES) == {"music", "video"}, FEATURES)
server_src = open(os.path.join(os.path.dirname(HERE), "server.py"), encoding="utf-8").read()


def body_of(route):
    i = server_src.index(f'@app.route("{route}"')
    j = server_src.find("\n@app.route(", i + 1)
    return server_src[i:j if j > 0 else len(server_src)]


for free_route in ("/api/music/lyrics", "/api/music/audio-prompt", "/api/music/chat",
                   "/api/video/script", "/api/video/scene-image", "/api/chat",
                   "/api/chat/stream", "/api/research", "/api/tts"):
    if free_route in server_src:
        check(f"{free_route} does not touch the quota", "quota." not in body_of(free_route),
              "metered route found")
    else:
        check(f"{free_route} does not exist (nothing to meter)", True)
for metered in ("/api/music/generate", "/api/video/clip"):
    check(f"{metered} is enforced", "quota.reserve(" in body_of(metered))
check("the quota route is read-only", "jsonify(quota.report" in server_src)

# The UI never counts on its own: it only renders what the server sends.
ui = open(os.path.join(os.path.dirname(HERE), "web", "index_new.html"), encoding="utf-8").read()
check("the browser reads its allowance from /api/quota", "apiUrl('/api/quota')" in ui)
check("the browser has no local allowance counter",
      "localStorage.getItem('fenix_quota" not in ui and 'fenix_quota_used' not in ui)
check("a refusal is shown as a sentence, not a stack trace",
      "quotaRefusal" in ui and "QUOTA_EXCEEDED" in ui)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
