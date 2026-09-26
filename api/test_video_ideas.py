"""
Fenix Video — idea suggestions.

The point of this suite is the cost. A suggestion must never spend brain
quota, because the brain is the scarcest resource in Fenix and the suggestion
button sits in front of the least important screen in the studio. It also
must be honest: the ideas really belong to the format that was asked for, and
the same person does not get a different three on every page load.

Run:  python3 api/test_video_ideas.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-ideas-test-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["QUOTA_ENABLED"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "fenix-video", "api"))
sys.path.insert(0, HERE)

import brain  # noqa: E402

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


print("every format has a real bank of starting points")
check("all three formats have ideas", set(brain.IDEAS) == set(brain.FORMATS),
      sorted(brain.IDEAS))
for key, bank in brain.IDEAS.items():
    check(f"{key} has at least 3 ideas", len(bank) >= 3, len(bank))
    check(f"{key} has no duplicates", len(set(bank)) == len(bank),
          len(bank) - len(set(bank)))
    check(f"{key} ideas are non-empty strings",
          all(isinstance(i, str) and len(i.strip()) > 12 for i in bank))
    check(f"{key} ideas are specific, not vague",
          all(len(i.split()) >= 5 for i in bank),
          [i for i in bank if len(i.split()) < 5][:2])

print("ideas belong to the format that was asked for")
for key in brain.FORMATS:
    got = brain.ideas(key, 3, "caller-1")
    check(f"{key}: the ideas come from that bank's format", all(i in brain.IDEAS[key] for i in got), got)
check("a bad format falls back instead of failing",
      brain.ideas("not-a-format", 3, "c") == brain.ideas(brain.DEFAULT_FORMAT, 3, "c"))
check("an empty format falls back",
      brain.ideas("", 3, "c") == brain.ideas(brain.DEFAULT_FORMAT, 3, "c"))

print("the same caller keeps the same suggestions")
check("a reload does not shuffle", brain.ideas("ship", 3, "user-42") == brain.ideas("ship", 3, "user-42"))
check("two callers differ", brain.ideas("ship", 3, "user-42") != brain.ideas("ship", 3, "user-43"))
check("rotating gives a different set", brain.ideas("ship", 3, "user-42|2") != brain.ideas("ship", 3, "user-42"))
check("rotation still stays inside the bank",
      set(brain.ideas("ship", 3, "user-42|2")) <= set(brain.IDEAS["ship"]))

print("the count is honoured and never overflows")
check("one idea", len(brain.ideas("mood", 1, "c")) == 1)
check("three ideas", len(brain.ideas("mood", 3, "c")) == 3)
check("an absurd count is clamped to the bank",
      len(brain.ideas("mood", 999, "c")) == len(brain.IDEAS["mood"]))
check("a zero or junk count still gives something", len(brain.ideas("mood", 0, "c")) >= 1)
check("no bank returns a repeated idea",
      len(set(brain.ideas("mood", 999, "c"))) == len(brain.IDEAS["mood"]))

print("the route serves them without touching the brain")
import server  # noqa: E402

server.music_hosts = lambda: []
server.video_hosts = lambda: []
server.app.config["TESTING"] = True
client = server.app.test_client()

calls = {"n": 0}
real_ideas = server._video_brain().ideas


def counting_ideas(*a, **kw):
    calls["n"] += 1
    return real_ideas(*a, **kw)


server._video_brain().ideas = counting_ideas

r = client.get("/api/video/ideas?format=ship")
d = r.get_json()
check("GET /api/video/ideas answers 200", r.status_code == 200, r.status_code)
check("it returns ideas", isinstance(d.get("ideas"), list) and d["ideas"], d)
check("it says which format answered", d.get("format") == "ship", d)
check("it admits no brain was used", d.get("brain_used") is False, d)
check("the ideas are the right ones", all(i in brain.IDEAS["ship"] for i in d["ideas"]), d)

r = client.get("/api/video/ideas?format=mood&count=5")
d = r.get_json()
check("count is honoured by the route", len(d["ideas"]) == 5, d)
r = client.get("/api/video/ideas?count=nonsense")
check("a junk count does not break it", r.status_code == 200 and r.get_json()["ideas"], r.status_code)

print("suggestions never touch the quota")
q = client.get("/api/quota", headers={"X-Forwarded-For": "203.0.113.55"}).get_json()
before_music = q["features"]["music"]["used"]
before_video = q["features"]["video"]["used"]
for _ in range(6):
    client.get("/api/video/ideas?format=explain")
after = client.get("/api/quota", headers={"X-Forwarded-For": "203.0.113.55"}).get_json()
check("music quota is untouched", after["features"]["music"]["used"] == before_music,
      (before_music, after["features"]["music"]))
check("video quota is untouched", after["features"]["video"]["used"] == before_video,
      (before_video, after["features"]["video"]))
check("the full allowance is still there",
      after["features"]["music"]["remaining"] == after["features"]["music"]["limit"], after)
src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
_i = src.index("def api_video_ideas")
_j = src.index("\n@app.route(", _i + 1)
_body = src[_i:_j]
# Look at code, not prose: the docstring says "costs no brain quota", which
# would trip a naive substring check.
_code = "\n".join("" if ln.strip().startswith(("#", '"', "'")) else ln
                 for ln in _body.splitlines())
check("the route code contains no quota call", "quota." not in _code,
      "metered route found")
check("the route code does not reach a paid or free brain", "_brains_call" not in _code)

print("the client asks for free ideas and never invents them")
ui = open(os.path.join(ROOT, "web", "index_new.html"), encoding="utf-8").read()
check("the chips read the server's list", "apiUrl('/api/video/ideas?format=" in ui)
check("the chip fills the textarea", "topic.value = b.textContent" in ui)
check("a different seed gives a different set", "loadIdeas(true)" in ui)
check("changing format reloads the ideas", "loadIdeas(false)" in ui)
check("no idea text is hard-coded in the page",
      not any(i[:28] in ui for i in brain.IDEAS["mood"]), "an idea is baked into the HTML")
check("a failed fetch does not break the studio",
      "catch (e) { box.innerHTML = ''" in ui)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
