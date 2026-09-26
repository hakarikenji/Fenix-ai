"""Contract test: does server.py talk to the audio worker correctly?

Runs a fake worker that speaks the real contract (POST / -> audio/wav) and
checks the server's happy path, its not-audio rejection, and its 503 path.
"""
import io
import struct
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
# This suite is about the engine contract, not the allowance. Metering is
# exercised on its own in api/test_quota*.py, so it is off here or the repeated
# stub calls would spend a real (shared, loopback) allowance and each later
# check would be refused for the wrong reason.
os.environ["QUOTA_ENABLED"] = "0"
import server as s  # noqa: E402

FAKE_URL = None
MODE = {"v": "wav"}


def wav_bytes(n_samples=32000):
    pcm = b"\x00\x01" * n_samples
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 32000, 64000, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"status":"up","service":"fenix-music-gen","model":"facebook/musicgen-small"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        if MODE["v"] == "wav":
            data = wav_bytes()
            ct = "audio/wav"
        elif MODE["v"] == "html":
            data = b"<!DOCTYPE html><html>gateway timeout</html>" * 60
            ct = "text/html"
        else:
            data = b'{"error":"no worker"}' * 100
            ct = "application/json"
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
    ok = ok and cond
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


# 1. happy path
MODE["v"] = "wav"
s.os.environ["MUSIC_GEN_URL"] = FAKE_URL
s.os.environ.pop("HF_TOKEN", None)
r = c.post("/api/music/generate", json={"prompt": "dark phonk beat", "duration": 8})
d = r.get_json()
check("generate returns 200", r.status_code == 200, str(d)[:120])
check("reports the worker as source", d.get("source") == "worker", str(d.get("source")))
check("returns a track url", bool(d.get("url")) and d["url"].startswith("/audio/"), str(d.get("url")))
check("byte count is real", isinstance(d.get("bytes"), int) and d["bytes"] > 1000, str(d.get("bytes")))
name = (d.get("url") or "").rsplit("/", 1)[-1]
r2 = c.get(f"/audio/{name}")
check("generated track downloads", r2.status_code == 200, str(r2.status_code))
check("download is real wav", r2.data[:4] == b"RIFF", repr(r2.data[:4]))

# 2. the name must be scoped, not a raw /tmp file
r3 = c.get("/audio/passwd")
check("refuses unrelated /tmp files", r3.status_code == 404, str(r3.status_code))

# 3. worker returns HTML -> caught, not served as a track
MODE["v"] = "html"
r4 = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("rejects non-audio body", r4.status_code == 502, str(r4.status_code))

# 4. worker down -> 503 with the real reason
MODE["v"] = "wav"
s.os.environ["MUSIC_GEN_URL"] = "http://127.0.0.1:1/"
r5 = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("dead worker -> 503", r5.status_code == 503, str(r5.status_code))
d5 = r5.get_json()
check("503 names the real failure", bool(d5.get("last_failure")), str(d5.get("last_failure"))[:90])
_msg = f"{d5.get('error', '')} {d5.get('detail', '')}".lower()
check("503 points at the audio engine", "audio engine" in _msg, _msg[:80])
check("503 does NOT point at the lyrics brain",
      "music_brain_modal" not in d5.get("detail", ""), "ok")

# 5. no worker configured at all (empty string turns the shared host off)
s.os.environ.pop("MUSIC_GEN_URL", None)
s.os.environ["MUSIC_GEN_SPACE_URL"] = ""
r6 = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("unconfigured -> 503", r6.status_code == 503, str(r6.status_code))

# 6. generator-check
s.os.environ["MUSIC_GEN_URL"] = FAKE_URL
r7 = c.get("/api/music/generator-check")
d7 = r7.get_json()
check("generator-check reaches the worker", d7.get("worker_reachable") is True, str(d7)[:100])
s.os.environ.pop("MUSIC_GEN_URL", None)
s.os.environ["MUSIC_GEN_SPACE_URL"] = ""
r8 = c.get("/api/music/generator-check")
check("generator-check explains when off",
      "audio engine" in (r8.get_json().get("problem") or "").lower(),
      str(r8.get_json().get("problem"))[:80])

# 7. with nothing set at all, the app still has a working engine
s.os.environ.pop("MUSIC_GEN_SPACE_URL", None)
d = c.get("/api/music/generator-check").get_json()
check("a default engine is configured", d.get("space_url_set") is True, str(d)[:90])
check("the default is labelled a shared host", d.get("shared_host") is True, str(d.get("problem"))[:90])

srv.shutdown()
print("\nALL CONTRACT TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
