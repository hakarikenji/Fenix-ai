"""
The production package must be runnable, not just importable in the dev shell.

A container host does three things the local preview never does: it copies a
fixed file list into the image, it starts `gunicorn server:app` rather than
`python server.py`, and it hands the process a $PORT. Anything missing from
that path fails on Render and nowhere else, which is the worst place to find
out.

This also guards the honest answer to "will my data still be there tomorrow",
because a free instance's disk is not the user's disk and the training counter
is the whole point of the training data.

Run:  python3 api/test_container.py
"""
import ast
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="fenix-container-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["PORT"] = "8010"
# Defaults, not a deployment: storage is temporary and the proxy is not trusted
# unless a host says so.
os.environ.pop("FENIX_TRUST_PROXY", None)
os.environ.pop("FENIX_DATA_DURABLE", None)

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


print("the container can be built from what is in the repo")
dockerfile = read("Dockerfile")
check("a Dockerfile exists", bool(dockerfile))
check("it does not copy secrets", ".env" not in dockerfile)
check("it runs gunicorn, not the dev server", '"gunicorn"' in dockerfile)
check("it runs as a non-root user", "USER fenix" in dockerfile)
check("it declares a health check", "HEALTHCHECK" in dockerfile)
check("the health check hits a route the app really has", "/healthz" in dockerfile)
ignore = read(".dockerignore")
check("a .dockerignore exists", bool(ignore))
check("the data dir is never baked into the image",
      ".data" in ignore and ".env" in ignore)
# Compare whole lines: "api" is a substring of "fenix-video/api", so a naive
# membership test would call a correct .dockerignore broken.
ignore_lines = {ln.strip() for ln in ignore.splitlines() if ln.strip()}
for rel in ("api", "fenix-video/api", "web", "server.py"):
    check(".dockerignore does not exclude %s" % rel,
          rel not in ignore_lines, sorted(ignore_lines))
check(".dockerignore re-admits the video brain the server imports",
      "fenix-video/**" in ignore_lines and "!fenix-video/api/**" in ignore_lines)

print("the file list the image copies is complete")
for rel in ("server.py", "gunicorn.conf.py", "requirements.txt",
            "api/", "fenix-video/api/", "web/"):
    check("Dockerfile copies %s" % rel, rel in dockerfile)
for rel in ("server.py", "gunicorn.conf.py", "requirements.txt",
            "api", "fenix-video/api", "web"):
    check("and %s really exists" % rel, os.path.exists(os.path.join(ROOT, rel)))
check("the video brain package is the one server.py imports",
      os.path.exists(os.path.join(ROOT, "fenix-video", "api", "brain.py")))

print("gunicorn is configured for how the host will run it")
conf = read("gunicorn.conf.py")
check("it reads the injected $PORT", 'os.environ.get("PORT"' in conf)
check("it binds every interface", 'bind = "0.0.0.0:' in conf)
check("the request timeout clears the longest model call", "timeout = 300" in conf)
check("there is a Procfile too", "gunicorn" in read("Procfile"))

print("the blueprint says the things a free instance gets wrong")
blueprint = read("render.yaml")
check("a render blueprint exists", bool(blueprint))
check("it uses the free plan", "plan: free" in blueprint)
check("it polls a real health path", "healthCheckPath: /healthz" in blueprint)
check("it trusts the proxy in front of it", 'FENIX_TRUST_PROXY' in blueprint
      and 'value: "1"' in blueprint)
check("it declares the storage as temporary", 'FENIX_DATA_DURABLE' in blueprint
      and 'value: "0"' in blueprint)
check("secrets are never committed", "sync: false" in blueprint)
check("the admin email is listed so it is not forgotten",
      "FENIX_ADMIN_EMAIL" in blueprint)

print("the app answers as the container will run it")
import server  # noqa: E402

client = server.app.test_client()
check("/healthz answers", client.get("/healthz").status_code == 200)
r = client.get("/")
check("/ serves the app", r.status_code == 200 and b"fenix" in r.data.lower(),
      r.status_code)
brains = client.get("/api/brains")
check("/api/brains reports storage", brains.status_code == 200
      and "storage" in brains.get_json(), brains.status_code)

print("storage durability is measured, never assumed")
st = server.storage_state()
check("storage_state exists", isinstance(st, dict), st)
check("a fresh install is assumed temporary", st["durable"] is False, st)
check("it explains what that means", len(st.get("note", "")) > 40)
os.environ["FENIX_DATA_DURABLE"] = "1"
check("a host that declares a volume is believed",
      server.storage_state()["durable"] is True)
os.environ.pop("FENIX_DATA_DURABLE")

print("the front end says so where the promise is made")
ui = read(os.path.join("web", "index_new.html"))
check("the training sheet warns about a temporary disk",
      "temporary disk" in ui and "d.storage.durable" in ui)
check("the server sends that flag with the readiness numbers",
      '"storage": storage_state()' in read("server.py"))
check("and with the brain report, which is where honesty already lives",
      read("server.py").count('"storage": storage_state()') >= 2)

print("no syntax regression")
for rel in ("server.py", "api/quota.py", "api/db.py", "api/store.py"):
    try:
        ast.parse(read(rel))
        check("%s parses" % rel, True)
    except SyntaxError as e:
        check("%s parses" % rel, False, e)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
