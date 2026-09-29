"""
No feature may be complete on the server and unreachable from the product.

This project has shipped that failure three times, and each time silently:
  - a tool registry with five working tools and no button,
  - a training-data export with no way to download it,
  - a whole Evolution panel whose functions lived in the legacy page.

Nothing raised. The code was there, the tests were green, and the user simply
had no way to reach any of it. So the property is now asserted directly: every
route the server serves must be called by the front end, or appear on a short
allowlist that says exactly why not.

Run:  python3 api/test_dead_features.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")

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


UI = "".join(read(n) for n in ("index_new.html", "studio-live.js"))
server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()

# Routes that are correct without a browser caller. Each needs a reason, so
# this list cannot quietly grow into a graveyard.
ALLOW = {
    "/": "the page itself",
    "/legacy": "kept for old bookmarks",
    "/sw.js": "fetched by the browser, not the page",
    "/manifest.json": "fetched by the browser, not the page",
    "/healthz": "infrastructure probe",
    "/api/<path:_any>": "CORS preflight",
    "/api/tools/<tool_name>": "tool dispatch for an agent; the browser reads the catalog via /api/brains",
    "/api/tools": "catalog; the same list is served inside /api/brains",
    "/audio/<path:name>": "streamed to an <audio> element by URL",
    "/clip/<path:name>": "streamed to a <video> element by URL",
}

routes = set()
for m in re.finditer(r'@app\.route\(\s*"([^"]+)"', server):
    routes.add(m.group(1))


def norm(p):
    return re.sub(r"<[^>]*>", "*", p).rstrip("/") or "/"


def covered_by_ui(route):
    """Does any front-end call match this route?

    Calls appear as a literal path, as a literal plus a query string, or as a
    literal prefix with a dynamic id appended (`'/api/evolution/insight/' + id`).
    """
    r = norm(route)
    if r.endswith("*"):
        prefix = re.escape(r[:-1])
        if re.search(r"""['"]%s[^'"]*['"]\s*\+\s""" % prefix, UI):
            return True
    pat = re.escape(r).replace(re.escape("*"), r"[^/]*")
    # allow a query string on the call: '/api/training-data?meta=1'
    return bool(re.search(r"""['"]%s(?:\?[^'"]*)?['"]""" % pat, UI))


print("every server route is reachable from the product")
dead = []
for route in sorted(routes):
    if route in ALLOW:
        continue
    if not covered_by_ui(route):
        dead.append(route)
for route in sorted(routes & set(ALLOW)):
    check("allowlisted with a reason: %s" % route, route in ALLOW, ALLOW.get(route, ""))
check("no route is unreachable from the product", not dead, ", ".join(dead))

print("the allowlist itself is not a graveyard")
for route in sorted(ALLOW):
    if route in routes:
        continue
    check("allowlist entry still exists: %s" % route, False, "the route is gone — delete the entry")

print("the features that were dead are now rendered")
for label, needle in [
    ("training readiness", "loadTrainingData"),
    ("the JSONL download", "td-download"),
    ("the rated-pairs export", "td-ratings"),
    ("the context preview", "td-context-btn"),
    ("the memory reindex", "memReindexBtn"),
    ("the tool catalog", "renderTools"),
    ("the free-scaling panel", "renderFreeScaling"),
    ("the music brain chain", "renderBrainChain"),
    ("the evolution panel", "loadEvolution"),
]:
    check(label + " is wired", needle in UI, needle)

print("the newly reachable features are honest about their own state")
check("training readiness is measured, not assumed", "'/api/training-data?meta=1'" in UI)
check("the download says how many pairs it got", "X-Fenix-Pairs" in UI)
check("a refused export shows the server's own reason", "d.error" in UI)
check("the context preview shows labels, not a blob", "s.label" in UI)
check("a provider chip follows the server's own rule", "rate-limited" in UI)

print("nothing regressed into a second definition")
for name in ("streamAI", "loadEvolution", "renderTools", "loadTrainingData", "api_chat"):
    pattern = r"(?:async )?function %s\(" % name if name != "api_chat" else r"^def api_chat\("
    hay = UI if name != "api_chat" else server
    hits = len(re.findall(pattern, hay, re.M))
    check("%s is defined exactly once" % name, hits == 1, "found %d" % hits)

print("the dead brain chain is not retried on every request")
check("a cool-off exists", "BRAIN_DEAD_TTL_S" in server and "_brain_dead" in server)
check("a 404 is distinguished from a busy host", "urllib.error.HTTPError" in server)
check("a host that answers is un-marked", '_brain_mark(base_url, "", True)' in server)
check("what each host is doing is reported", '"chain"' in server and "_brain_errors" in server)

print("no Python function is defined and never called again")
# A function carrying a decorator is bound at import time by the framework
# (every Flask route, @lru_cache, @retry), so it has no textual caller and is
# not dead. Everything else must be referenced somewhere.
import ast  # noqa: E402

py_files = ["server.py"] + sorted(
    os.path.join("api", f) for f in os.listdir(os.path.join(ROOT, "api"))
    if f.endswith(".py"))
sources = {p: open(os.path.join(ROOT, p), encoding="utf-8").read() for p in py_files}
# callers that live outside the server: tests, notebooks, deploy scripts, docs
outside = ""
for d in ("scripts", "fenix-brain-space", "fenix-core-lora", "fenix-music",
          "fenix-video", "fenix-music-apk-kit", ".github"):
    for dp, dns, fns in os.walk(os.path.join(ROOT, d)):
        dns[:] = [x for x in dns if x not in ("__pycache__", "node_modules", ".git")]
        for fn in fns:
            if fn.endswith((".py", ".ipynb", ".sh", ".yml", ".md")):
                try:
                    outside += open(os.path.join(dp, fn), encoding="utf-8", errors="ignore").read()
                except OSError:
                    pass

# Names bound by a framework rather than by a caller.
DYNAMIC_OK = {"main", "read", "write", "generate", "reply", "load_engine", "health"}

dead_fns = []
for path, text in sources.items():
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.decorator_list or node.name in DYNAMIC_OK:
            continue
        if node.name.startswith("test_"):
            continue
        refs = sum(len(re.findall(r"\b%s\b" % re.escape(node.name), t))
                   for t in sources.values())
        refs += len(re.findall(r"\b%s\b" % re.escape(node.name), outside))
        if refs <= 1:  # only the definition itself
            dead_fns.append("%s:%d %s" % (path, node.lineno, node.name))
check("no function is defined and never called", not dead_fns, "; ".join(dead_fns))

# The APK shipped the wrong screen for weeks: the WebView opens
# assets/public/index.html, and that file is the legacy UI the server serves at
# /legacy. index_new.html — the UI the user actually sees — was in the APK the
# whole time, unused. The build now copies it over after `cap sync`; if that
# step is ever dropped, the APK silently goes back to a product with no Music,
# no Video and no builder, and no test anywhere would notice.
print("the APK opens the current UI, not the legacy screen")
apk_wf = open(os.path.join(ROOT, ".github", "workflows", "build-apk.yml"),
              encoding="utf-8").read()
_COPIES = "cp web/index_new.html" in apk_wf
check("the build copies index_new.html over index.html",
      _COPIES and "android/app/src/main/assets/public/index.html" in apk_wf)
# A crash here would itself be a failing signal, but a missing step should read
# as a failed check, not a traceback that hides the rest of the suite.
check("it happens after `cap sync`, which would otherwise undo it",
      _COPIES and apk_wf.index("npx cap sync") < apk_wf.index("cp web/index_new.html"))
check("the legacy screen is still reachable on the server",
      "legacy_index" in server and '"/legacy"' in server)
# The two files are genuinely different, so the copy is not a no-op.
check("index.html is not just a copy of index_new.html",
      read("index.html") != read("index_new.html"),
      "they are identical — the APK problem cannot happen, but /legacy is a lie")

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
