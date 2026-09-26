"""Contract test: does server.py talk to the clip engine correctly?

Runs a fake engine that speaks the real contract (POST / -> video/mp4) and
checks the happy path, the not-a-video rejection, the honest 503, and that
clips are only ever served for names the server generated.
"""
import os
import struct
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
# This suite checks the clip engine contract, not the allowance. Metering has
# its own suites (api/test_quota*.py); with it on, the repeated stub calls here
# would spend a shared loopback allowance and later checks would be refused for
# the wrong reason.
os.environ["QUOTA_ENABLED"] = "0"
import server as s  # noqa: E402

MODE = {"v": "mp4"}


def mp4_bytes(payload=40000):
    # A real mp4 carries an 'ftyp' box at offset 4. The rest only has to be
    # big enough that the size checks do not reject it.
    return b"\x00\x00\x00\x20ftypisom" + b"\x00" * payload


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"status":"ok","service":"fenix-video-gen","engine":"text-to-video","ready":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        if MODE["v"] == "mp4":
            data, ct = mp4_bytes(), "video/mp4"
        elif MODE["v"] == "html":
            data, ct = b"<!DOCTYPE html><html>gateway timeout</html>" * 60, "text/html"
        else:
            data, ct = b'{"error":"no engine"}' * 100, "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), H)
FAKE_URL = f"http://127.0.0.1:{srv.server_port}/"
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)
c = s.app.test_client()
ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


# 1. happy path
MODE["v"] = "mp4"
s.os.environ["VIDEO_GEN_URL"] = FAKE_URL
r = c.post("/api/video/clip", json={"prompt": "neon street in rain", "seconds": 4})
d = r.get_json()
check("clip returns 200", r.status_code == 200, str(d)[:140])
check("reports the engine as source", d.get("source") == "clip-engine", str(d.get("source")))
check("returns a clip url", bool(d.get("url")) and d["url"].startswith("/clip/"), str(d.get("url")))
name = (d.get("url") or "").rsplit("/", 1)[-1]
r2 = c.get(f"/clip/{name}")
check("generated clip downloads", r2.status_code == 200, str(r2.status_code))
check("download is real mp4", r2.data[4:8] == b"ftyp", repr(r2.data[4:8]))

# 2. the name must be scoped, not a raw /tmp file
check("refuses unrelated /tmp files", c.get("/clip/passwd").status_code == 404)

# 3. engine returns HTML -> caught, not served as a clip
MODE["v"] = "html"
r3 = c.post("/api/video/clip", json={"prompt": "x"})
check("rejects non-video body", r3.status_code == 502, str(r3.status_code))

# 4. engine down -> 502 with the real reason
MODE["v"] = "mp4"
s.os.environ["VIDEO_GEN_URL"] = "http://127.0.0.1:1/"
r4 = c.post("/api/video/clip", json={"prompt": "x"})
check("dead engine -> 502", r4.status_code == 502, str(r4.status_code))
check("502 names the real failure", bool(r4.get_json().get("last_failure")),
      str(r4.get_json().get("last_failure"))[:90])

# 5. no engine configured at all
s.os.environ.pop("VIDEO_GEN_URL", None)
s.os.environ["VIDEO_GEN_SPACE_URL"] = ""
r5 = c.post("/api/video/clip", json={"prompt": "x"})
d5 = r5.get_json()
check("unconfigured -> 503", r5.status_code == 503, str(r5.status_code))
check("503 says the stills still work", "stills" in (d5.get("detail") or ""), str(d5.get("detail"))[:80])

# 6. prompt required
r6 = c.post("/api/video/clip", json={"prompt": "  "})
check("empty prompt -> 400", r6.status_code == 400, str(r6.status_code))

# 7. clip-check
s.os.environ["VIDEO_GEN_URL"] = FAKE_URL
d7 = c.get("/api/video/clip-check").get_json()
check("clip-check reaches the engine", d7.get("worker_reachable") is True, str(d7)[:100])
s.os.environ.pop("VIDEO_GEN_URL", None)
s.os.environ["VIDEO_GEN_SPACE_URL"] = ""
d8 = c.get("/api/video/clip-check").get_json()
check("clip-check explains when unset",
      "stills" in (d8.get("problem") or ""), str(d8.get("problem"))[:80])

# 8. /api/brains advertises the clip engine honestly
s.os.environ["VIDEO_GEN_URL"] = FAKE_URL
check("brains reports clip_gen", c.get("/api/brains").get_json().get("clip_gen") is True)
s.os.environ.pop("VIDEO_GEN_URL", None)
s.os.environ["VIDEO_GEN_SPACE_URL"] = ""
check("brains reports no clip_gen when unset",
      c.get("/api/brains").get_json().get("clip_gen") is False)

srv.shutdown()
print("\nALL CLIP CONTRACT TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
