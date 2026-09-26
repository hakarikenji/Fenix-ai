"""
Fenix — shipping readiness.

Two things that are not bugs but are the difference between a working product
and a broken one:

1. Hosting could not run `pip install`, so a deploy would have shipped without
   any of the runtime dependencies and rendered a blank page.
2. The storyboard promised "about a minute per scene" for a button whose
   engine could refuse every job, and walked all twelve scenes failing one by
   one instead of stopping at the first refusal.

Run:  python3 api/test_ship_readiness.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-ship-test-")
os.environ["FENIX_DATA_DIR"] = _TMP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def deps(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            out.append(line.lower())
    return sorted(out)


print("the hosting build can install what the app imports")
check("api/requirements.txt exists — hosting looks for it there",
      os.path.exists(os.path.join(ROOT, "api", "requirements.txt")))
check("the root requirements.txt is kept",
      os.path.exists(os.path.join(ROOT, "requirements.txt")))
if os.path.exists(os.path.join(ROOT, "api", "requirements.txt")):
    a, b = deps(os.path.join(ROOT, "api", "requirements.txt")), deps(os.path.join(ROOT, "requirements.txt"))
    check("the two dependency lists are identical", a == b, f"api={a} root={b}")
    joined = " ".join(a)
    for mod, label in (("flask", "flask"), ("gunicorn", "gunicorn"),
                       ("google-genai", "google-genai"), ("sentry", "sentry")):
        check(f"{label} is declared for the hosted build", mod in joined)

src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
third_party = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", src, re.M))
KNOWN_LOCAL = {"common", "db", "store", "memory", "evolution", "research", "brain_health",
               "free_brains", "free_brains_cache", "identity_guard", "gradio_client",
               "tool_registry", "context_engine", "observability", "quota", "enhance",
               "library", "library_apply", "semantic_memory", "video_brain", "workspace"}
stdlib = {"json", "os", "sys", "time", "re", "base64", "hashlib", "urllib", "pathlib",
          "threading", "secrets", "sqlite3", "subprocess", "typing", "datetime", "math",
          "importlib", "traceback", "tempfile", "shutil", "itertools", "functools",
          "collections", "textwrap", "random", "string", "uuid", "struct", "io",
          "concurrent", "unittest", "warnings", "statistics", "copy", "glob", "errno",
          "mimetypes", "uuid", "asyncio", "socket", "signal", "contextlib", "abc"}
external = sorted(m for m in third_party
                  if m not in stdlib and m not in KNOWN_LOCAL and m != "server")
declared = " ".join(deps(os.path.join(ROOT, "api", "requirements.txt"))) if \
    os.path.exists(os.path.join(ROOT, "api", "requirements.txt")) else ""
alias = {"dotenv": "python-dotenv", "google": "google-genai", "genai": "google-genai",
         "PIL": "Pillow", "sentry_sdk": "sentry-sdk", "flask_cors": "flask-cors",
         "sentence_transformers": "sentence-transformers", "numpy": "numpy"}
missing = [m for m in external
           if not any(a in declared for a in (m, alias.get(m, ""), m.replace("_", "-")))]
check("every third-party import in server.py is declared", not missing, f"missing: {missing}")
print(f"  (external imports found: {external or 'none'})")

print("the engine reports which kind of clip engine it is")
check("clip_engine_state exists", "def clip_engine_state()" in src)
check("it distinguishes own / shared / off",
      '"own"' in src and '"shared"' in src and '"off"' in src)
check("/api/brains publishes it", '"clip_gen_state": clip_engine_state()' in src)
check("/api/video/clip-check publishes it", '"mode": clip_engine_state()' in src)
check("it never promises a shared host will render", "Reachability is not a guarantee" in src)
check("a refusal is flagged for the client", '"engine_refused": engine_refused' in src)

print("the storyboard no longer promises what it cannot deliver")
ui = open(os.path.join(ROOT, "web", "index_new.html"), encoding="utf-8").read()
markup = re.sub(r"<style[^>]*>[\s\S]*?</style>", "",
                re.sub(r"<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?</script>", "", ui))
check("the page never states a per-scene time up front",
      "it takes about a minute per scene" not in markup,
      "an unconditional timing promise is still in the markup")
check("the note now promises only what always works",
      "exportable as it stands" in markup, "the reassuring part is missing")
check("the timing is conditional on a dedicated engine",
      "dedicated engine" in ui and "a minute" in ui)

print("the loop stops at the first refusal instead of failing every scene")
check("an engine refusal is captured", "VD.engineRefused = d" in ui)
check("it is detected from the status code", "d.__status >= 500" in ui)
check("the loop breaks on it", "if (VD.quotaHit || VD.engineRefused) break;" in ui)
check("the user is told what still works",
      "Your film is still" in ui and "export" in ui)
check("it does not blame the user's allowance for an engine failure",
      ui.count("quotaRefusal('video'") == 1, "quota blamed for an engine refusal")

print("the copy is decided by a real check, not by an assumption")
check("there is a probe", "async function checkMotionEngine()" in ui)
check("it asks the server", "apiUrl('/api/video/clip-check')" in ui)
check("it runs when the storyboard appears", "checkMotionEngine();" in ui)
check("each engine mode has its own wording", "'shared'" in ui and "'own'" in ui and "'off'" in ui)
check("the slow-engine flag drives the progress line", "VD.motionSlow ?" in ui)

print("nothing in the client decides what the engine can do")
check("the client does not set an engine flag itself",
      "localStorage.setItem('fenix_video_url" not in ui)
check("it does not claim a scene will always render",
      "every scene will have real motion" not in ui)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
