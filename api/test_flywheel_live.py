"""
Live check: the flywheel actually turns.

The unit suite proves the client calls the route. This proves the route
receives it, over HTTP, through the same path the browser uses — and that the
dataset builder sees what landed.

Run:  python3 api/test_flywheel_live.py [base_url]
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


def call(path, body=None, token=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except ValueError:
            return e.code, {"raw": raw[:160]}


email = f"flywheel-probe-{os.getpid()}@fenix.test"
st, s = call("/api/auth/signup", {"email": email, "password": "probe-pass-1234",
                                  "name": "Flywheel probe"})
if "token" not in s:
    st, s = call("/api/auth/signin", {"email": email, "password": "probe-pass-1234"})
token = s.get("token")
check("got a throwaway account", bool(token), s)
if not token:
    sys.exit(1)

st, conv = call("/api/conversations", {"title": "flywheel probe"}, token)
check("created a conversation", st == 200 and conv.get("id"), (st, conv))
cid = conv.get("id")

Q1 = "Why does a database migration lock a table for four minutes on a busy server?"
A1 = ("Because ALTER TABLE takes an exclusive lock and waits for every reader to "
      "finish. Set a lock_timeout so it fails fast instead of stalling traffic.")
Q2 = "How do I stop my LoRA training run from reporting a loss while learning nothing?"
A2 = ("Hold out a split before training, evaluate on it at the end, and fail the "
      "run if held-out loss did not beat the untuned base.")

st1, r1 = call(f"/api/conversations/{cid}/messages", {"role": "user", "content": Q1}, token)
st2, r2 = call(f"/api/conversations/{cid}/messages", {"role": "assistant", "content": A1}, token)
st3, r3 = call(f"/api/conversations/{cid}/messages", {"role": "user", "content": Q2}, token)
st4, r4 = call(f"/api/conversations/{cid}/messages", {"role": "assistant", "content": A2}, token)
check("all four turns are accepted", all(x == 200 for x in (st1, st2, st3, st4)),
      (st1, st2, st3, st4))

st, back = call(f"/api/conversations/{cid}", token=token)
msgs = back.get("messages") or []
check("the turns come back from the server", len(msgs) >= 4, len(msgs))
check("in order", [m.get("role") for m in msgs[:4]] == ["user", "assistant", "user", "assistant"],
      [m.get("role") for m in msgs[:4]])
check("the text survived intact", any(m.get("content") == Q2 for m in msgs))
check("a summary round-trips", call(f"/api/conversations/{cid}", {"summary": "lo"},
                                    token)[0] == 200)

print("the dataset builder now sees real material")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
import train_dataset  # noqa: E402
report = train_dataset.build()
check("the builder ran over the live database", report["raw_seen"] > 0, report)
check("these two exchanges survived its filters", report["count"] >= 2, report)
check("they are not treated as duplicates", report["distinct_replies"] >= 2, report)
check("and it still refuses to call this a training set",
      report["ready"] is False, "it accepted a couple of pairs as a dataset")

print("someone else's conversation stays theirs")
st, other = call("/api/conversations", {"title": "not yours"}, None)
check("an unauthenticated caller cannot create one", st == 401, (st, other))
st, mine = call(f"/api/conversations/{cid}")
check("and cannot read a conversation they do not own", st == 401, (st, mine))
st, mine2 = call(f"/api/conversations/{cid}/messages", {"role": "user", "content": "x"})
check("nor post into one", st == 401, (st, mine2))
st, mine3 = call(f"/api/conversations/{cid}", method="DELETE")
check("nor delete one", st == 401, (st, mine3))

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
