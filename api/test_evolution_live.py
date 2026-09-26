"""
Two features were complete on the server and dead in the product. Both are
guarded here, because each one failed silently — no error, no warning, just a
button that did nothing and a profile that never learned anything.

1. `web/stream-fix.js` was loaded by no page at all, yet it defined
   `window.streamAI` from an older build. Any cached page that still fetched it
   overwrote the real streamer with one that omitted `conversationId` (so server
   -side conversation persistence died) and reported every failure as
   "Server unreachable" — which is the message users actually saw.

2. The Evolution panel shipped with its sheet, its CSS and all five server
   routes, but the functions behind them lived only in the legacy
   `web/index.html`. `index_new.html` called `loadEvolution()` and never defined
   it, so tapping "Evolution" threw a ReferenceError. Worse, the only automatic
   `evolution_store.observe()` call sat inside an unrouted `api_chat` that a
   route decorator had already shadowed, so the learning path had never run.

Run:  python3 api/test_evolution_live.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
UI_PATH = os.path.join(WEB, "index_new.html")

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def read(name):
    p = os.path.join(WEB, name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def body_of(src, name):
    """The source of one top-level JS function, up to the next one."""
    m = re.search(r"^(?:async )?function %s\(" % re.escape(name), src, re.M)
    if not m:
        return ""
    nxt = re.search(r"^(?:async )?function \w+\(", src[m.end():], re.M)
    return src[m.start(): m.end() + nxt.start()] if nxt else src[m.start():]


def py_body_of(src, name):
    """The source of one top-level Python function, up to the next one."""
    m = re.search(r"^def %s\(" % re.escape(name), src, re.M)
    if not m:
        return ""
    nxt = re.search(r"^(?:def |@app\.)", src[m.end():], re.M)
    return src[m.start(): m.end() + nxt.start()] if nxt else src[m.start():]


def loads_script(name):
    """True only if the file really pulls stream-fix.js in as a resource.
    A comment that explains the removal is not a load."""
    text = read(name)
    return bool(re.search(r"""(?:src\s*=\s*|importScripts\(\s*)['"][^'"]*stream-fix""", text))


src = open(UI_PATH, encoding="utf-8").read()
server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
sw = read("sw.js")

# ---------------------------------------------------------------- no orphans
print("no orphaned script can shadow the real chat streamer")
orphan = os.path.join(WEB, "stream-fix.js")
check("stream-fix.js is gone", not os.path.exists(orphan))
for name in ("index_new.html", "index.html", "studio-live.js", "sw.js"):
    check("nothing loads stream-fix.js (%s)" % name, not loads_script(name))

print("the page defines the streamer itself, so nothing has to patch it")
stream_fn = body_of(src, "streamAI")
check("streamAI is defined in the page", bool(stream_fn))
check("it is the only definition of streamAI", src.count("function streamAI") == 1,
      "a second definition would shadow it again")
check("it sends the conversation id", "conversationId" in stream_fn,
      "without it nothing is stored server-side")
check("it reads research sources", "'sources'" in stream_fn)
check("a failed stream falls back to the whole-reply endpoint",
      "callAI(" in src and "await callAI(" in src)
check("it does not report every failure as 'unreachable'",
      "Server unreachable" not in stream_fn,
      "that message hid the real status from the user")

# ------------------------------------------------------------ cache hygiene
print("a stale shell cannot be served again")
cache = re.search(r'CACHE\s*=\s*"([^"]+)"', sw)
check("the service worker has a cache name", bool(cache))
if cache:
    check("the cache name was bumped past v28", cache.group(1) != "fenix-v28-training-export",
          "the stale shell is still reachable: " + cache.group(1))
check("old caches are deleted on activate",
      "k !== CACHE" in sw and "caches.delete" in sw)
check("API calls are never cached", 'url.includes("/api/")' in sw)

# ------------------------------------------------------- the panel is wired
print("the Evolution panel is actually wired")
evo = body_of(src, "loadEvolution")
check("loadEvolution is defined in the page", bool(evo),
      "it is called by the #openEvoBtn binding but was never defined")
check("it is defined exactly once", src.count("async function loadEvolution") == 1)
check("the button that opens it exists", 'id="openEvoBtn"' in src)
check("the button calls it", "loadEvolution()" in src)
check("it reads the profile", "/api/evolution'" in evo)
check("it renders the insights", "d.insights" in evo and "evo-item" in evo)
check("it renders the log", "d.log" in evo and "log-item" in evo)
check("it shows how much evidence is still needed", "min_evidence" in evo)
check("an insight can be removed", "data-edel" in evo and "/api/evolution/insight/" in evo)
check("the toggle is bound", "evoSeg" in src and "/api/evolution/toggle" in src)
check("a reset is bound", "evoClear" in src and "/api/evolution/clear" in src)
check("every element it touches is guarded", "if (!seg || !insBox || !logBox) return;" in evo)
check("it needs no account to not crash", "if (!USER) return;" in evo)
check("user text is escaped", "escHtml(" in evo)
check("the sheet it renders into exists", 'id="evoSheet"' in src
      and 'id="evoInsights"' in src and 'id="evoLog"' in src)

# -------------------------------------------------------- the learning path
print("the profile actually learns during a real conversation")
obs = py_body_of(server, "_evolution_observe")
check("_evolution_observe exists", bool(obs))
builder = py_body_of(server, "_chat_sse_response")
check("it is called exactly once", builder.count("_evolution_observe(") == 1)
check("it sits in the builder both transports use", bool(obs) and "_evolution_observe(" in builder)
check("it is called with the real turn, not a guess",
      "_evolution_observe(token, user, message," in builder)
check("it needs a signed-in user", "user" in obs)
check("it only learns inside a project", "project_id" in obs)
check("it requires a real signal, not every message",
      "any(word in message.lower() for word in" in obs)
check("it never invents a trait on its own", "evidence" not in obs.split("reason")[0].lower()
      or "MIN_EVIDENCE" in open(os.path.join(HERE, "evolution.py"), encoding="utf-8").read())
check("evolution can be switched off", "is_enabled" in obs)
check("a failure here cannot cost the reply", "except Exception" in obs)

print("the observation is withheld until there is proof")
ev = open(os.path.join(HERE, "evolution.py"), encoding="utf-8").read()
check("an insight needs MIN_EVIDENCE observations before it activates",
      "MIN_EVIDENCE" in ev and "ins[\"active\"] = True" in ev)
check("every insight is inspectable and deletable", "def update_insight" in ev
      and "def delete_insight" in ev)
check("nothing is recorded while disabled",
      'if not data.get("enabled", True):' in ev)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
