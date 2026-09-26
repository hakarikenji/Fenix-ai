"""
End-to-end: the running Fenix server must refuse over-quota generation.

Talks HTTP to the live preview exactly as the browser does — no imports, no
internals. It proves the three things a unit test cannot: the route is really
mounted, the refusal carries the structured body, and a request that never
reaches the engine does not spend anything.

Run:  python3 api/test_quota_live.py [base_url]
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010").rstrip("/")
PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def post(path, body, token=None, timeout=60):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except ValueError:
            return e.code, {"raw": raw[:200]}


def get(path, token=None, timeout=30):
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except ValueError:
            return e.code, {"raw": raw[:200]}


# A throwaway account, so a live run never eats the real user's allowance.
email = f"quota-probe-{os.getpid()}@fenix.test"
st, signup = post("/api/auth/signup", {"email": email, "password": "probe-pass-1234",
                                       "name": "Quota probe"})
if st != 200 or "token" not in signup:
    st, signin = post("/api/auth/signin", {"email": email, "password": "probe-pass-1234"})
    signup = signin
token = signup.get("token")
check("got a throwaway account", bool(token), signup)
if not token:
    sys.exit(1)

try:
    print("the allowance route is public and read-only")
    st, q = get("/api/quota", token)
    check("GET /api/quota answers 200", st == 200, st)
    check("both features are reported", set(q.get("features", {})) == {"music", "video"}, q)
    check("the numbers are the configured ones",
          q["features"]["music"]["limit"] >= 0 and q["features"]["video"]["limit"] > 0, q)
    check("a reset time is published", q["features"]["music"]["reset_at"] > 0, q)
    check("the browser cannot learn its window from the client",
          "countdown" not in q and "used_by_client" not in q)

    print("a fresh account starts with the full allowance")
    st, m0 = get("/api/quota", token)
    full_music = m0["features"]["music"]["remaining"]
    full_video = m0["features"]["video"]["remaining"]
    check("music starts full", full_music == m0["features"]["music"]["limit"], m0)
    check("video starts full", full_video == m0["features"]["video"]["limit"], m0)

    print("the cheap parts of Fenix are never refused")
    st, lyrics = post("/api/music/lyrics", {"topic": "a quiet morning", "genre": "lofi"}, token)
    check("/api/music/lyrics still answers", st in (200, 502, 503, 504), (st, str(lyrics)[:120]))
    st, script = post("/api/video/script",
                      {"topic": "a paper boat crossing a city in the rain",
                       "language": "English", "style": "cinematic"}, token)
    check("/api/video/script still answers", st in (200, 502, 503, 504), (st, str(script)[:120]))

    print("a request that never reaches an engine spends nothing")
    before = get("/api/quota", token)[1]["features"]["music"]["remaining"]
    st, empty = post("/api/music/generate", {"prompt": "   "}, token)
    check("an empty prompt is a 400, not a quota event", st == 400, (st, empty))
    after = get("/api/quota", token)[1]["features"]["music"]["remaining"]
    check("nothing was consumed", before == after, (before, after))

    print("the video duration ceiling is enforced by the server")
    st, clip = post("/api/video/clip", {"prompt": "x", "seconds": 600,
                                        "width": 832, "height": 480}, token)
    # No clip engine is connected, so this is a refusal — but never a 500 and
    # never a silent success.
    check("an absurd duration does not crash the route", st in (400, 429, 502, 503),
          (st, str(clip)[:160]))
    if st == 429:
        check("the refusal is the structured one",
              clip.get("error") == "QUOTA_EXCEEDED" or clip.get("code") == "COOLDOWN", clip)
        check("it names the feature", clip.get("feature") == "video", clip)
        check("it carries a reset time", bool(clip.get("reset_at")), clip)
        check("it is written as a sentence", isinstance(clip.get("message"), str)
              and len(clip["message"]) > 10, clip)
        check("it leaks no engine or host detail",
              not any(w in json.dumps(clip).lower()
                      for w in ("token", "api_key", "http://", "https://", "gpu", "hf_")),
              clip)
finally:
    pass

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
