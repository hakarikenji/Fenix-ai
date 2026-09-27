"""
The deployment target imports a WSGI file; it never starts a process.

Everything about a PythonAnywhere failure is invisible from the dev shell: the
app is imported rather than run, so a missing sys.path entry only shows up on
their host, the data directory is whatever the environment says it is, and a
hardcoded /tmp looks fine right up until a clip URL 404s because the file is in
a directory the app does not own.

Run:  python3 api/test_wsgi_host.py
"""
import ast
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_TMP = tempfile.mkdtemp(prefix="fenix-wsgi-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["PORT"] = "8010"
os.environ.pop("FENIX_TRUST_PROXY", None)
os.environ.pop("FENIX_DATA_DURABLE", None)
os.environ.pop("FENIX_MEDIA_DIR", None)

sys.path.insert(0, HERE)
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


def read(name):
    p = os.path.join(ROOT, name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


print("the file the host actually imports exposes an application")
wsgi = read("fenix_wsgi.py")
check("fenix_wsgi.py exists", bool(wsgi))
check("it exposes `application`", "as application" in wsgi)
check("it also answers to `app`", "\napp = application" in wsgi)
check("it puts the repo on the path", "sys.path.insert" in wsgi)
check("it puts api/ on the path", '"api"' in wsgi)
check("it imports server, not a server", "from server import app" in wsgi)
# Prose-proof: the docstring explains that gunicorn is deliberately absent, so
# the word appears in the file. Look at the code, not the text.
_wsgi_tree = ast.parse(wsgi)
_calls = {n.func.attr for n in ast.walk(_wsgi_tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
_imported = {a.name.split(".")[0] for n in ast.walk(_wsgi_tree)
             if isinstance(n, ast.Import) for a in n.names}
_imported |= {n.module.split(".")[0] for n in ast.walk(_wsgi_tree)
              if isinstance(n, ast.ImportFrom) and n.module}
check("it never starts a server", "run" not in _calls, sorted(_calls))
check("it does not import a server runner", not _imported & {"gunicorn", "uwsgi"})

print("it really imports on this Python")
try:
    ns = {"__file__": os.path.join(ROOT, "fenix_wsgi.py"), "__name__": "fenix_wsgi_probe"}
    exec(compile(wsgi, "fenix_wsgi.py", "exec"), ns)
    check("the file executes and yields a callable", callable(ns.get("application")))
    import flask
    check("it is the Flask app", isinstance(ns["application"], flask.Flask))
    check("it serves the front end", any(
        str(r) == "/" for r in ns["application"].url_map.iter_rules()))
    check("it answers the health check the host may poll", any(
        str(r) == "/healthz" for r in ns["application"].url_map.iter_rules()))
except Exception as e:  # noqa: BLE001
    check("the file executes and yields a callable", False, repr(e))

print("generated media is not left in a directory the app does not own")
server_src = read("server.py")
check("the media directory is declared", "MEDIA_DIR =" in server_src)
check("it defaults under the data directory",
      'os.environ.get("FENIX_DATA_DIR", ".data")' in server_src)
check("it can be moved by the host", 'FENIX_MEDIA_DIR' in server_src)
hard = [ln for ln in server_src.splitlines() if '"/tmp"' in ln]
# one /tmp may remain: the fallback when the chosen directory cannot be made.
check("no route writes to a hardcoded /tmp", len(hard) <= 1, hard)
check("the clip write uses it", 'Path(MEDIA_DIR) / f"fenix-clip-' in server_src)
check("the audio write uses it", 'Path(MEDIA_DIR) / f"fenix-music-' in server_src)
check("both serve from it", server_src.count("send_from_directory(MEDIA_DIR") == 2)

print("the filename guards still hold, because the directory now holds data too")
check("a clip must still be one this server made",
      'base.startswith("fenix-clip-")' in server_src)
check("a track must still be one this server made",
      'base.startswith("fenix-music-")' in server_src)
check("and both are still reduced to a basename", server_src.count("os.path.basename(name)") == 2)

print("the storage answer is right for this host")
import server  # noqa: E402

st = server.storage_state()
check("storage is never assumed durable", st["durable"] is False, st)
check("it explains itself", len(st.get("note", "")) > 40)
os.environ["FENIX_DATA_DURABLE"] = "1"
check("a host that declares durability is believed",
      server.storage_state()["durable"] is True)
os.environ.pop("FENIX_DATA_DURABLE")
check("media landed under the data dir", server.MEDIA_DIR.startswith(_TMP),
      server.MEDIA_DIR)

print("the app answers the way the host will call it")
client = server.app.test_client()
check("/healthz answers", client.get("/healthz").status_code == 200)
check("/ serves the app", client.get("/").status_code == 200)
brains = client.get("/api/brains")
check("/api/brains reports storage",
      brains.status_code == 200 and "storage" in brains.get_json(), brains.status_code)

print("config for hosts that cannot run Fenix is gone, not left to rot")
for gone in ("Dockerfile", "render.yaml", "Procfile", ".dockerignore"):
    check("%s is removed" % gone, not os.path.exists(os.path.join(ROOT, gone)),
          "it is still present but no host will ever build it")
check("the deployment guide is written down", os.path.exists(
    os.path.join(ROOT, "DEPLOY-PYTHONANYWHERE.md")))
guide = read("DEPLOY-PYTHONANYWHERE.md")
check("it names the environment variables the host needs",
      "FENIX_DATA_DIR" in guide and "GEMINI_API_KEY" in guide)
check("it states the outbound allowlist limit", "allowlist" in guide.lower())
check("it states the single-worker limit", "worker" in guide.lower())
check("it says what to verify after deploying", "Verify after deploying" in guide)

print("no syntax regression")
for rel in ("server.py", "fenix_wsgi.py", "api/quota.py", "api/db.py", "api/store.py"):
    try:
        ast.parse(read(rel))
        check("%s parses" % rel, True)
    except SyntaxError as e:
        check("%s parses" % rel, False, e)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
